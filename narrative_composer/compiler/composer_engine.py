"""
Closed-Loop Generation & Auto-Repair Engine.
Orchestrates topological beat execution, AST linting, automated repair prompts, and state mutation.
"""

from __future__ import annotations
from collections import Counter
from typing import Callable, List, Optional, Set, Dict, Any
from ..models.causal_dag import CausalDAG, StoryBeatNode, StateDelta
from ..models.epistemic import EpistemicMatrix, EpistemicBelief
from ..models.spatial_fsm import SpatialGraph, ItemLifecycle, BodySlot
from ..models.character import DialecticCharacterNode
from ..models.ast_nodes import ASTNodeType
from ..parser.fountain_lexer import FountainParser
from ..linter.screenplay_linter import ScreenplayLinter
from ..linter.rules import LintViolation
from .context_projector import ContextProjector


class PendingBeatReview(RuntimeError):
    """A mechanically checked draft is available but has no author decision."""
    def __init__(self, proposal):
        super().__init__('Beat draft requires author review before state is committed')
        self.proposal = proposal


class NarrativeComposerEngine:
    def __init__(
        self,
        dag: CausalDAG,
        epistemic: EpistemicMatrix,
        spatial: SpatialGraph,
        llm_generate_fn: Optional[Callable[[str], str]] = None,
        provider: Optional[Any] = None,
        character_nodes: Optional[Dict[str, DialecticCharacterNode]] = None,
        review_fn: Optional[Callable[[dict], bool]] = None,
        graph: Optional[Any] = None,
        canon: str = 'hot_scoomp_main',
        initial_states: Optional[Dict[str, str]] = None,
        reviewed_observations: Optional[List[Dict[str, Any]]] = None,
        hypothetical_states: Optional[Dict[str, str]] = None,
    ):
        self.dag = dag
        self.epistemic = epistemic
        self.spatial = spatial
        self.review_fn, self.graph, self.canon = review_fn, graph, canon
        self.initial_states = initial_states or {}
        self.reviewed_observations = reviewed_observations or []
        self.hypothetical_states = hypothetical_states or {}

        # Character data must be selected explicitly for this project revision.
        self.character_nodes = character_nodes if character_nodes is not None else {}

        # Generation function / provider resolution
        if llm_generate_fn is not None:
            self.llm_generate = llm_generate_fn
        elif provider is not None:
            if hasattr(provider, "generate_text"):
                self.llm_generate = provider.generate_text
            else:
                raise ValueError("Provided provider does not have a generate_text method.")
        else:
            from ..prose.providers.venice import VeniceProseProvider
            venice = VeniceProseProvider()
            self.llm_generate = venice.generate_text

        self.linter = ScreenplayLinter(self.epistemic, self.spatial)
        self.committed_script_buffer: List[str] = []
        self.discovered_features: Set[str] = set()

    def run_pipeline(self, max_retries: int = 3, punch_up: bool = False) -> str:
        """
        Executes the entire script DAG topologically until all beats pass validation.
        Returns the consolidated screenplay text.
        """
        while True:
            beat = self.dag.get_next_actionable_beat()
            if not beat:
                if not self.dag.is_all_completed():
                    raise RuntimeError('Story execution blocked with incomplete beats')
                break

            self.process_beat(beat, max_retries=max_retries, punch_up=punch_up)

        return "\n\n".join(self.committed_script_buffer)

    def process_beat(self, beat: StoryBeatNode, max_retries: int = 3, punch_up: bool = False) -> str:
        """
        Generates and validates a single beat, retrying with targeted repair diagnostics if violations occur.
        If punch_up is True, runs a comedic enhancement pass over the verified draft.
        """
        self._check_preconditions(beat)
        prior_tail = self._get_dialogue_tail(10)
        base_prompt = ContextProjector.compile_beat_prompt(
            beat=beat,
            epistemic=self.epistemic,
            spatial=self.spatial,
            prior_dialogue_tail=prior_tail,
            character_nodes=self.character_nodes
        )

        prompt = base_prompt
        attempt = 0

        # Determine active room from primary character
        primary_char = beat.active_characters[0] if beat.active_characters else "STELLA"
        active_room = self.spatial.get_character_room(primary_char)
        if active_room == "UNKNOWN_ROOM":
            active_room = "living_room"

        while attempt < max_retries:
            attempt += 1
            raw_output = self.llm_generate(prompt)
            ast = FountainParser.parse(raw_output)

            committed_full_text = "\n".join(self.committed_script_buffer)
            violations = self.linter.lint_beat(
                ast=ast,
                active_room_id=active_room,
                prior_committed_script=committed_full_text,
                discovered_features=self.discovered_features
            )

            # Separate hard errors from soft warnings (Rule 11 produces WARNING, so only ERROR triggers repair)
            errors = [v for v in violations if v.severity == "ERROR"]
            if not raw_output.strip():
                raise ValueError('Empty generated beat')

            if not errors:
                # PASS: Optional Comedic Punch-Up & Quality Enhancement Pass
                if punch_up:
                    raw_output = self._punch_up_beat(
                        beat=beat,
                        draft=raw_output,
                        active_room=active_room,
                        committed_full_text=committed_full_text
                    )

                prior_graph_errors = []
                state_assumptions = []
                if self.graph is not None:
                    from narrative_composer.graph.extract import extract_run
                    from narrative_composer.graph.checks import run_checks
                    from narrative_composer.graph.resolver import EntityResolver
                    before = FountainParser.parse(committed_full_text)
                    before_run = extract_run(before, self.graph, self.canon, 'before', initial_states=self.initial_states,
                                             reviewed_observations=self.reviewed_observations)
                    prior_graph_errors = [v for v in run_checks(before_run, self.graph, self.canon, before) if v.severity == 'ERROR']
                    current = {eid: self.initial_states.get(eid, f"{eid}.state.{actor.attributes.get('canon_base_states', {}).get(self.canon, actor.base_state)}")
                               for eid, actor in self.graph.entities.items()}
                    for instance in before_run.states:
                        current[instance.entity] = instance.state_id
                    state_assumptions = [{'entity': eid, 'selected': state, 'accepted': current.get(eid),
                                          'status': 'pending form and transition review'}
                                         for eid, state in self.hypothetical_states.items() if current.get(eid) != state]
                    for eid, state in self.hypothetical_states.items():
                        if current.get(eid) == state and any(
                                issue.rule_id == 'G9_REVIEWED_STATE_CAUSE_PENDING' and issue.entity == eid and
                                f'Author reviewed {state} ' in issue.message for issue in before_run.issues):
                            state_assumptions.append({'entity': eid, 'selected': state, 'accepted': state,
                                                      'status': 'transition cause pending review'})
                    assembled = FountainParser.parse(committed_full_text + '\n\n' + raw_output)
                    assembled_errors = [v for v in run_checks(extract_run(assembled, self.graph, self.canon, 'beat',
                                    initial_states=self.initial_states, reviewed_observations=self.reviewed_observations),
                                    self.graph, self.canon, assembled) if v.severity == 'ERROR']
                    def identity(v):
                        return (v.rule_id, v.line, v.entity, v.message)
                    remaining = Counter(identity(v) for v in prior_graph_errors)
                    graph_errors = []
                    for violation in assembled_errors:
                        key = identity(violation)
                        if remaining[key]:
                            remaining[key] -= 1
                        else:
                            graph_errors.append(violation)
                    resolver = EntityResolver(self.graph, self.canon)
                    def hypothetical_cue(violation):
                        if violation.rule_id != 'G2_CUE_STATE_MISMATCH':
                            return False
                        element = next((item for item in assembled if item.line_number == violation.line and
                                        item.node_type == ASTNodeType.CHARACTER), None)
                        if element is None:
                            return False
                        eid, slug = resolver.resolve_cue(element.content)
                        return bool(eid and slug and self.hypothetical_states.get(eid) == f'{eid}.state.{slug}' and
                                    any(item['entity'] == eid for item in state_assumptions))
                    blocking = [violation for violation in graph_errors if not hypothetical_cue(violation)]
                    if blocking:
                        raise ValueError('; '.join(v.message for v in blocking))

                from narrative_composer.workspace import digest
                proposal = {'beat_id': beat.beat_id, 'text': raw_output,
                    'base_revision': digest({'world': self.spatial.model_dump(), 'knowledge': self.epistemic.model_dump(),
                                             'prior_text': self.committed_script_buffer, 'beat':beat.model_dump()}),
                    'decision':'pending review', 'validation':'passed', 'meaning':'pending author review',
                    'graph_validation':('hypothetical form pending review' if state_assumptions else
                        ('no new errors' if prior_graph_errors else 'passed')) if self.graph is not None else 'not run',
                    'state_assumptions': state_assumptions, 'eligible': not state_assumptions,
                    'preexisting_graph_errors':len(prior_graph_errors)}
                if state_assumptions and self.review_fn is not None:
                    raise ValueError('The hypothetical form differs from accepted story state; review the form and transition before applying')
                if state_assumptions or self.review_fn is None or not self.review_fn(proposal):
                    raise PendingBeatReview(proposal)
                self._check_preconditions(beat)
                self._commit_beat_success(beat, raw_output)
                return raw_output

            # FAIL: Construct targeted auto-repair prompt using hard errors
            repair_report = ScreenplayLinter.format_diagnostic_report(errors)
            prompt = (
                f"{base_prompt}\n\n"
                f"{repair_report}\n\n"
                f"--- REJECTED DRAFT (CONTAINED CONTINUITY ERRORS) ---\n"
                f"{raw_output}\n\n"
                f"--- INSTRUCTION ---\n"
                f"Rewrite the rejected draft to resolve every violation while preserving all valid dialogue."
            )

        raise RuntimeError(
            f"Beat '{beat.beat_id}' failed verification after {max_retries} attempts.\n"
            f"Last violations: {[v.diagnostic_message for v in errors]}"
        )

    def _check_preconditions(self, beat):
        self.dag.validate_graph()
        if any(not self.dag.beats[p].is_completed for p in beat.prerequisite_beat_ids):
            raise ValueError('Prerequisite beat is incomplete')
        for required in beat.required_beliefs:
            value = required['min_belief']
            wanted = EpistemicBelief[value] if isinstance(value, str) and value in EpistemicBelief.__members__ else EpistemicBelief(value)
            if self.epistemic.get_belief(required['character_id'], required['fact_id']) != wanted:
                raise ValueError(f"Required belief unmet: {required['fact_id']}")
        for required in beat.required_prop_states:
            prop = self.spatial.items.get(required['item_id'])
            if prop is None or prop.lifecycle != ItemLifecycle(required['required_lifecycle']):
                raise ValueError(f"Required prop state unmet: {required['item_id']}")
        for update in beat.state_delta.epistemic_updates:
            if update['fact_id'] not in self.epistemic.facts:
                raise ValueError('State delta references an unknown fact')
            EpistemicBelief(update['belief'])
        for update in beat.state_delta.prop_mutations:
            if update['item_id'] not in self.spatial.items:
                raise ValueError('State delta references an unknown prop')
            if 'lifecycle' in update:
                ItemLifecycle(update['lifecycle'])
            if 'slot' in update:
                BodySlot(update['slot'])
            if 'charges_delta' in update:
                if type(update['charges_delta']) is not int:
                    raise ValueError('charges_delta must be an integer')
            if update.get('held_by') is not None and not isinstance(update['held_by'], str):
                raise ValueError('held_by must be a character ID or null')

    def _punch_up_beat(
        self,
        beat: StoryBeatNode,
        draft: str,
        active_room: str,
        committed_full_text: str
    ) -> str:
        """
        Enhancement pass: Sharpens comedic dialogue volleys, trims fat, and lands a punchy button line.
        Guarantees that 0-error linter compliance is strictly preserved.
        """
        punch_up_prompt = (
            f"=== COMEDIC ENHANCEMENT & PUNCH-UP PASS ===\n"
            f"SLUGLINE: {beat.slugline}\n"
            f"ACTIVE CHARACTERS: {', '.join(beat.active_characters)}\n"
            f"DRAMATIC GOAL: {beat.dramatic_goal}\n\n"
            f"--- VERIFIED BASE DRAFT ---\n"
            f"{draft}\n\n"
            f"--- ENHANCEMENT INSTRUCTIONS ---\n"
            f"1. Improve the rhythm only where it serves this particular scene.\n"
            f"2. Preserve the author's tone, actions, character roles, dialogue meaning and dramatic goal.\n"
            f"3. Do not invent events, personality traits, props, or a required joke.\n"
            f"4. Output standard Fountain screenplay text without markdown code fences.\n"
            f"5. Preserve continuity and prop lifecycles; do not introduce forbidden tokens."
        )
        try:
            enhanced = self.llm_generate(punch_up_prompt)
            if not isinstance(enhanced, str) or not enhanced.strip():
                return draft
            ast = FountainParser.parse(enhanced)
            violations = self.linter.lint_beat(
                ast=ast,
                active_room_id=active_room,
                prior_committed_script=committed_full_text,
                discovered_features=self.discovered_features
            )
            errors = [v for v in violations if v.severity == "ERROR"]
            if not errors:
                return enhanced
        except Exception:
            pass
        return draft

    def _commit_beat_success(self, beat: StoryBeatNode, text: str) -> None:
        """Commits verified beat text and applies StateDelta mutations to world models."""
        beat.generated_text = text
        beat.is_completed = True
        self.committed_script_buffer.append(text)

        # Log dialogue utterances into the Spatial Witness Log for cross-beat telepathy checks (Rule 10)
        ast = FountainParser.parse(text)
        primary_char = beat.active_characters[0] if beat.active_characters else "STELLA"
        active_room = self.spatial.get_character_room(primary_char)
        if active_room == "UNKNOWN_ROOM":
            active_room = "living_room"
        for node in ast:
            if node.node_type == ASTNodeType.DIALOGUE and node.speaker:
                self.spatial.record_utterance(node.line_number, node.speaker, active_room, node.content)

        delta = beat.state_delta

        # 1. Mutate Epistemic Matrix
        for update in delta.epistemic_updates:
            char_id = update["character_id"]
            fact_id = update["fact_id"]
            belief_val = update["belief"]
            self.epistemic.set_belief(char_id, fact_id, EpistemicBelief(belief_val))

        # 2. Mutate Spatial FSM & Props
        for p_mut in delta.prop_mutations:
            item_id = p_mut["item_id"]
            if item_id in self.spatial.items:
                item = self.spatial.items[item_id]
                if "lifecycle" in p_mut:
                    item.lifecycle = ItemLifecycle(p_mut["lifecycle"])
                if "charges_delta" in p_mut and item.charges_remaining is not None:
                    item.charges_remaining = max(0, item.charges_remaining + p_mut["charges_delta"])
                    if item.charges_remaining == 0:
                        item.lifecycle = ItemLifecycle.EXPENDED
                if "held_by" in p_mut:
                    item.held_by = p_mut["held_by"].upper() if p_mut["held_by"] else None
                if "slot" in p_mut:
                    item.equipped_slot = BodySlot(p_mut["slot"])

        # 3. Mutate Character Relocations
        for char_id, new_room in delta.character_relocations.items():
            self.spatial.move_character(char_id, new_room)

        # 4. Track newly observed visual features
        text_lower = text.lower()
        if "rocket ship" in text_lower or "rocket-ship" in text_lower:
            self.discovered_features.add("rocket_ships")

    def _get_dialogue_tail(self, num_lines: int = 10) -> str:
        """Returns the last N lines of committed text for prompt continuity."""
        if not self.committed_script_buffer:
            return ""
        all_lines = "\n".join(self.committed_script_buffer).strip().split("\n")
        non_empty = [l for l in all_lines if l.strip()]
        return "\n".join(non_empty[-num_lines:])
