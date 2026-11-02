import { Editor } from '@tiptap/core';
import { Paragraph } from '@tiptap/extension-paragraph';
import { UniqueID } from '@tiptap/extension-unique-id';
import { StarterKit } from '@tiptap/starter-kit';
import { Fragment, Slice } from '@tiptap/pm/model';
import { closeHistory } from '@tiptap/pm/history';

const NarrativeParagraph = Paragraph.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      layout: {
        default: 'body',
        parseHTML: element => element.getAttribute('data-layout') || 'body',
        renderHTML: attrs => ({ 'data-layout': attrs.layout }),
      },
      align: {
        default: 'left',
        parseHTML: element => element.getAttribute('data-align') || 'left',
        renderHTML: attrs => ({ 'data-align': attrs.align }),
      },
    };
  },
});

const kit = StarterKit.configure({
  paragraph: false, heading: false, blockquote: false, bulletList: false,
  orderedList: false, listItem: false, listKeymap: false, code: false,
  codeBlock: false, hardBreak: false, horizontalRule: false, link: false,
  dropcursor: false, gapcursor: false, trailingNode: false,
});

function projection(doc) {
  const lines = [];
  doc.forEach(node => lines.push(node.textContent));
  return lines.join('\n');
}

function positionAt(doc, index) {
  let cursor = 0;
  let result = null;
  doc.forEach((node, offset) => {
    if (result !== null) return;
    const end = cursor + node.textContent.length;
    if (index <= end) result = offset + 1 + index - cursor;
    cursor = end + 1;
  });
  if (result === null) throw new Error('Document position is outside the story');
  return result;
}

function marksForReplacement(doc, from, to) {
  let signature = null;
  let marks = null;
  doc.nodesBetween(from, to, (node, position) => {
    if (!node.isText || position >= to || position + node.nodeSize <= from) return;
    const current = JSON.stringify(node.marks.map(mark => mark.toJSON()));
    if (signature !== null && signature !== current) {
      throw new Error('Proposal crosses mixed formatting; edit it manually to preserve the styles.');
    }
    signature = current;
    marks = node.marks;
  });
  return marks || doc.resolve(from).marks();
}

function replaceText(state, from, to, value, preserveMarks = false) {
  const normalized = value.replace(/\r\n?/g, '\n');
  const transaction = state.tr;
  if (!normalized.includes('\n')) {
    if (preserveMarks && normalized) {
      const marks = marksForReplacement(state.doc, from, to);
      return transaction.replaceWith(from, to, state.schema.text(normalized, marks));
    }
    return transaction.insertText(normalized, from, to);
  }
  if (preserveMarks && from !== to) {
    let formatted = false;
    state.doc.nodesBetween(from, to, node => { if (node.isText && node.marks.length) formatted = true; });
    if (formatted) throw new Error('Proposal crosses formatted lines; edit it manually to preserve the styles.');
  }
  const nodes = normalized.split('\n').map(line =>
    state.schema.nodes.paragraph.create(null, line ? state.schema.text(line) : null));
  return transaction.replaceRange(from, to, new Slice(Fragment.fromArray(nodes), 1, 1));
}

function safePrefix(a, b) {
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  if (i && i < a.length && /[\uD800-\uDBFF]/.test(a[i - 1]) && /[\uDC00-\uDFFF]/.test(a[i])) i--;
  return i;
}

function prepareReplacement(editor, requested) {
  const current = projection(editor.state.doc);
  const target = requested.replace(/\r\n?/g, '\n');
  if (current === target) return null;
  const prefix = safePrefix(current, target);
  let suffix = 0;
  while (suffix < current.length - prefix && suffix < target.length - prefix &&
         current[current.length - 1 - suffix] === target[target.length - 1 - suffix]) suffix++;
  if (suffix && current.length - suffix > prefix &&
      /[\uD800-\uDBFF]/.test(current[current.length - suffix - 1]) &&
      /[\uDC00-\uDFFF]/.test(current[current.length - suffix])) suffix--;
  if (current.slice(prefix, current.length - suffix).includes('\n')) {
    throw new Error('Proposal would replace multiple paragraphs; edit it manually to preserve their layout.');
  }
  const from = positionAt(editor.state.doc, prefix);
  const to = positionAt(editor.state.doc, current.length - suffix);
  const transaction = replaceText(editor.state, from, to, target.slice(prefix, target.length - suffix), true);
  if (projection(transaction.doc) !== target) {
    throw new Error('This change cannot be applied without altering other text');
  }
  return closeHistory(transaction);
}

function makeEditor(element, document, onChange, onWarning) {
  let editor;
  editor = new Editor({
    element,
    extensions: [kit, NarrativeParagraph, UniqueID.configure({ types: ['paragraph'] })],
    content: document,
    enableContentCheck: true,
    onContentError: () => {
      onWarning('Unsupported document content; editing is stopped to protect it.');
      editor?.setEditable(false);
    },
    editorProps: {
      attributes: { 'aria-label': 'Editable story document', spellcheck: 'true' },
      handlePaste(view, event) {
        const clipboard = event.clipboardData;
        if (!clipboard) return false;
        event.preventDefault();
        if (!Array.from(clipboard.types).includes('text/plain')) {
          onWarning('Only text can be pasted here; the source clipboard was not changed.');
          return true;
        }
        const text = clipboard.getData('text/plain');
        const { from, to } = view.state.selection;
        view.dispatch(closeHistory(replaceText(view.state, from, to, text)));
        view.dispatch(closeHistory(view.state.tr).setMeta('addToHistory', false));
        if (Array.from(clipboard.types).includes('text/html')) {
          onWarning('Pasted text; clipboard formatting was not imported.');
        }
        return true;
      },
      handleDrop(view, event) {
        if (event.dataTransfer?.files?.length ||
            (!view.dragging && Array.from(event.dataTransfer?.types || []).includes('text/html'))) {
          event.preventDefault();
          onWarning('External rich content and files cannot be dropped here; paste plain text instead.');
          return true;
        }
        return false;
      },
    },
    onUpdate: ({ editor: current }) => onChange(projection(current.state.doc)),
  });
  return {
    editor,
    text: () => projection(editor.state.doc),
    json: () => editor.getJSON(),
    html: () => editor.getHTML(),
    prepare: text => prepareReplacement(editor, text),
    commit(transaction) {
      if (!transaction) return;
      if (!transaction.before.eq(editor.state.doc)) throw new Error('Document changed while the proposal was reviewed');
      editor.view.dispatch(transaction);
      editor.view.dispatch(closeHistory(editor.state.tr).setMeta('addToHistory', false));
    },
    setEditable: value => editor.setEditable(value, false),
    destroy: () => editor.destroy(),
  };
}

window.NarrativeRichEditor = { makeEditor };
