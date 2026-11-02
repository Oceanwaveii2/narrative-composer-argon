"""
Behavioral trait aggregator and Character Node compiler.
Merges multi-source SceneObservations into canonical DialecticCharacterNodes
with confidence scoring and emits review.md checklists.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from narrative_composer.models.character import (
    DialecticCharacterNode,
    DialecticPole,
    DialecticTrait,
    Provenance,
    SynthesisRule,
)


class TraitAggregator:
    """
    Aggregates scene-level observations across multiple sources into
    coherent, confidence-weighted DialecticCharacterNodes.
    """

    @staticmethod
    def load_observations_from_file(observations_json_path: str) -> List[Dict[str, Any]]:
        path = Path(observations_json_path)
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data.get("observations", [])

    @classmethod
    def compile_hayley_node(
        cls,
        observation_file_paths: List[str],
        output_json_path: Optional[str] = None,
        output_review_md: Optional[str] = None,
        source_character_ids: Optional[List[str]] = None,
    ) -> DialecticCharacterNode:
        """
        Compiles the canonical Hayley Smith Dialectic Character Node
        from ingested Hot Scoomp, Kardashian Inflate, and Boondocks observations.
        """
        all_obs: List[Dict[str, Any]] = []
        for p in observation_file_paths:
            all_obs.extend(cls.load_observations_from_file(p))

        # Separate traits by source and category
        kinematics_traits: List[DialecticTrait] = []
        idiolect_traits: List[DialecticTrait] = []
        status_traits: List[DialecticTrait] = []
        thesis_traits: List[DialecticTrait] = []
        antithesis_traits: List[DialecticTrait] = []

        trait_counter = 1

        for sc_obs in all_obs:
            src_id = sc_obs.get("source_id", "")
            s_id = sc_obs.get("scene_id", "")
            for char_data in sc_obs.get("characters", []):
                char_id = char_data.get("character_id", "")
                if char_id not in (source_character_ids or ['hayley']):
                    continue

                for cat_name in ["kinematics", "idiolect", "status_moves", "rationalization_patterns"]:
                    for item in char_data.get(cat_name, []):
                        prov = Provenance(
                            source_id=src_id,
                            scene_id=s_id,
                            evidence_start=item["evidence_start"],
                            evidence_end=item["evidence_end"],
                        )
                        t_obj = DialecticTrait(
                            trait_id=f"trait_{trait_counter:03d}",
                            category=item["category"],
                            description=item["trait"],
                            provenance=[prov],
                            recurrence_count=1,
                            confidence_score=0.0,  # Uncalibrated until evidence review; never fabricate certainty.
                            example_expression=item.get("example_paraphrase"),
                        )
                        trait_counter += 1

                        if cat_name == "kinematics":
                            kinematics_traits.append(t_obj)
                        elif cat_name == "idiolect":
                            idiolect_traits.append(t_obj)
                        elif cat_name == "status_moves":
                            status_traits.append(t_obj)
                        elif cat_name == "rationalization_patterns":
                            if "hot_scoomp" in src_id:
                                thesis_traits.append(t_obj)
                            else:
                                antithesis_traits.append(t_obj)

        # Build Thesis Pole (Crunchy Activist)
        thesis = DialecticPole(
            pole_name="Thesis: Crunchy Activist",
            core_drive="Moral and intellectual superiority through eco-righteousness, anti-capitalist critique, and organic purity.",
            vocabulary_domain=[
                "fair-trade",
                "bamboo",
                "systemic oppression",
                "corporate greed",
                "indigenous",
                "microplastics",
                "unethical labor",
                "investigative journalism",
            ],
            traits=thesis_traits,
        )

        # Build Antithesis Pole (Grotesque Luxury Influencer)
        antithesis = DialecticPole(
            pole_name="Antithesis: Grotesque Luxury Influencer",
            core_drive="Unbothered bodily vanity, treating physical mass as an elite commercial asset, expecting adoration.",
            vocabulary_domain=[
                "billion-dollar peach",
                "pop-and-lock",
                "brand-worthy",
                "calabasas",
                "aesthetic maintenance",
                "vocal fry",
                "luxury asset",
                "snack",
            ],
            traits=antithesis_traits,
        )

        # Build Comedic Synthesis Rules
        synthesis_rules = [
            SynthesisRule(
                rule_id="synth_01_moral_vanity_fusion",
                trigger="When someone critiques her absurd physical mass, vanity, or grotesque posture.",
                mechanism="Uses Thesis eco-activist vocabulary to defend and rationalize Antithesis bodily excess.",
                example_volley=(
                    "HAYLEY: 'Excuse me, but this peach is 100% sustainably farmed, fair-trade, "
                    "and non-exploitative! You're just uncomfortable seeing a woman seize the means of mass production!'"
                ),
            ),
            SynthesisRule(
                rule_id="synth_02_unbothered_deflection",
                trigger="When a physical disaster or supernatural event occurs in the room.",
                mechanism="Ignores the actual catastrophe to critique minor aesthetic details or assert dominance.",
                example_volley=(
                    "HAYLEY: 'Honestly, Stella, your energy is so toxic right now. "
                    "Like, my glutes literally cannot absorb your negative vibes.'"
                ),
            ),
        ]

        node = DialecticCharacterNode(
            character_id="hayley",
            display_name="Hayley Smith (Hot Scoomp Fox-Goddess)",
            version="1.0.0",
            thesis=thesis,
            antithesis=antithesis,
            synthesis_rules=synthesis_rules,
            kinematics=kinematics_traits,
            idiolect=idiolect_traits,
            status_moves=status_traits,
        )

        if output_json_path:
            out_file = Path(output_json_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as fh:
                fh.write(node.model_dump_json(indent=2))

        if output_review_md:
            cls.emit_review_checklist(node, output_review_md)

        return node

    @staticmethod
    def emit_review_checklist(node: DialecticCharacterNode, review_md_path: str) -> None:
        """
        Emits an interactive review markdown checklist for human auditing.
        Allows verifying each trait against ground-truth video timecodes (the 70% test).
        """
        lines = [
            f"# Character Node Audit & Provenance Review: {node.display_name}",
            f"**Node ID:** `{node.character_id}` | **Version:** `{node.version}`",
            "",
            "## 1. The Dialectic Engine (Core Comedy Logic)",
            f"* **Thesis (Activists):** {node.thesis.core_drive}",
            f"  * *Vocabulary Domain:* `{', '.join(node.thesis.vocabulary_domain)}`",
            f"* **Antithesis (Influencer):** {node.antithesis.core_drive}",
            f"  * *Vocabulary Domain:* `{', '.join(node.antithesis.vocabulary_domain)}`",
            "",
            "### Synthesis Rules (How Thesis Vocabulary Rationalizes Antithesis Vanity):",
        ]

        for sr in node.synthesis_rules:
            lines.extend([
                f"- **{sr.rule_id}**: {sr.mechanism}",
                f"  - *Trigger:* {sr.trigger}",
                f"  - *Example Volley:* {sr.example_volley}",
            ])

        lines.extend([
            "",
            "## 2. Behavioral Trait Verification Checklist (The 70% Test)",
            "Review each trait against the recorded footage at the timestamp below. Verify if behavior holds up:",
            "",
            "| Check | Trait ID | Category | Behavioral Mechanic | Source | Time Window |",
            "| :---: | :---: | :---: | :--- | :--- | :---: |",
        ])

        for t in node.all_traits():
            p_str = "None"
            t_str = "N/A"
            if t.provenance:
                p = t.provenance[0]
                p_str = f"`{p.source_id}` / `{p.scene_id}`"
                t_str = f"`{p.evidence_start:.1f}s - {p.evidence_end:.1f}s`"
            lines.append(f"| [ ] | `{t.trait_id}` | **{t.category}** | {t.description} | {p_str} | {t_str} |")

        lines.extend([
            "",
            "---",
            "### Audit Instructions:",
            "1. Check off each row `[x]` if the behavioral mechanic accurately describes the physical/vocal dynamic in the source video.",
            "2. If $\\ge 70\\%$ survive verification, this node is approved for production prompt injection.",
        ])

        out_path = Path(review_md_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
