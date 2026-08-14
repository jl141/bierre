/**
 * YAML for profile files: a dumper and a deliberately small parser.
 *
 * Why this exists at all. Profile import/export ships in both formats, and YAML
 * is the human one — it is what `profiles/*.yaml` already are, so an exported
 * file can be read, diffed and version-controlled by a researcher. There is no
 * build step and no npm in this project, so a vendored library is not an option:
 * it would mean auditing and updating a dependency used for two functions.
 *
 * What is supported, on purpose, is the subset `yaml.safe_dump` produces plus
 * the subset a hand-authored profile needs: block mappings, block sequences,
 * flow collections on one line, quoted and plain scalars, plain scalars folded
 * over several lines, block scalars (`|`, `>`), and comments.
 *
 * What is refused — loudly, with a line number — is everything that either has
 * no meaning in a profile or is a way to smuggle behaviour into a data file:
 * anchors and aliases (`&a` / `*a`, the billion-laughs vector), tags
 * (`!!python/object`, the reason `yaml.load` is banned in this project), merge
 * keys, explicit keys, indentation indicators, and multiple documents. Each
 * refusal is a readable error the import panel can show; ignoring one silently
 * would be worse, because the file would then import as something other than
 * what it says.
 *
 * Scalar resolution follows PyYAML (YAML 1.1) rather than the 1.2 core schema:
 * `yes`/`no`/`on`/`off` are booleans here because they are booleans in
 * `yaml.safe_load`, and both ends of an import have to agree on what a file
 * means. `bierre-ca` re-parses the upload and stays the authority.
 */

const MAX_DEPTH = 32;

/**
 * A byte-order mark is legal at the start of a UTF-8 file and is not data — an
 * editor on Windows adds one, and left in place it becomes part of the first
 * key. Built from a char code because a literal one is invisible in a diff.
 */
const BOM_PREFIX = new RegExp(`^${String.fromCharCode(0xfeff)}`);

/** PyYAML's bool resolver, verbatim. Bare `y` and `n` are *not* in it. */
const BOOL_TRUE = /^(?:true|True|TRUE|yes|Yes|YES|on|On|ON)$/;
const BOOL_FALSE = /^(?:false|False|FALSE|no|No|NO|off|Off|OFF)$/;
const NULL_SCALAR = /^(?:~|null|Null|NULL)$/;
const INTEGER = /^[-+]?\d+$/;
const FLOAT = /^[-+]?(?:\d+\.\d*|\.\d+)(?:[eE][-+]?\d+)?$|^[-+]?\d+[eE][-+]?\d+$/;

/** A plain scalar that would be read back as something other than a string. */
const RESERVED_PLAIN =
  /^(?:~|null|Null|NULL|true|True|TRUE|false|False|FALSE|yes|Yes|YES|no|No|NO|on|On|ON|off|Off|OFF)$/;
const NUMBER_LIKE = /^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$/;
/** Leading characters YAML reads as syntax rather than as text. */
const UNSAFE_FIRST = /^[-?:,[\]{}#&*!|>'"%@`\s]/;
/** `key: value` and `text # comment` hiding inside a plain scalar. */
const UNSAFE_INNER = /:\s|\s#|:$/;
const CONTROL_CHARS = /\p{Cc}/u;
const ESCAPABLE = /\p{Cc}/gu;

const SIMPLE_ESCAPES = { n: "\n", t: "\t", r: "\r", 0: "\0", '"': '"', "\\": "\\", "/": "/" };

/** Carries a line number, so an import failure can point into the file. */
export class YamlError extends Error {
  constructor(message, line = 0) {
    super(line ? `Line ${line}: ${message}` : message);
    this.name = "YamlError";
    this.line = line;
  }
}

// --- dump --------------------------------------------------------------------

/**
 * Serialise JSON-shaped data as block-style YAML.
 *
 * The layout matches `yaml.safe_dump(sort_keys=False)` — two-space mapping
 * indents, sequences at their parent key's column — so a file exported here and
 * a file written by the YAML repository do not differ in a diff.
 *
 * @param {*} value Objects, arrays, strings, finite numbers, booleans, null.
 * @returns {string} Text ending in a newline.
 */
export function dumpYaml(value) {
  const lines = [];
  emitNode(value, 0, lines);
  return `${lines.join("\n")}\n`;
}

function emitNode(value, indent, out) {
  if (isMapping(value)) {
    emitMapping(value, indent, out);
  } else if (Array.isArray(value)) {
    if (!value.length) out.push(`${pad(indent)}[]`);
    else emitSequence(value, indent, out);
  } else {
    out.push(pad(indent) + formatScalar(value));
  }
}

function emitMapping(map, indent, out) {
  const entries = Object.entries(map).filter(([, item]) => item !== undefined);
  if (!entries.length) {
    out.push(`${pad(indent)}{}`);
    return;
  }

  for (const [key, item] of entries) {
    const prefix = `${pad(indent)}${formatScalar(String(key))}:`;
    if (isMapping(item) && Object.keys(item).length) {
      out.push(prefix);
      emitMapping(item, indent + 2, out);
    } else if (Array.isArray(item) && item.length) {
      out.push(prefix);
      // PyYAML keeps `- ` at the parent key's column rather than indenting it.
      emitSequence(item, indent, out);
    } else {
      out.push(`${prefix} ${formatLeaf(item)}`);
    }
  }
}

function emitSequence(list, indent, out) {
  for (const item of list) {
    const nestedBlock =
      (isMapping(item) && Object.keys(item).length) || (Array.isArray(item) && item.length);

    if (nestedBlock) {
      // The block's first line sits after the dash; the rest keep the
      // indentation the recursive call already gave them.
      const nested = [];
      emitNode(item, indent + 2, nested);
      out.push(`${pad(indent)}- ${nested[0].slice(indent + 2)}`, ...nested.slice(1));
    } else {
      out.push(`${pad(indent)}- ${formatLeaf(item)}`);
    }
  }
}

/** A value in a position where an empty collection has to be written inline. */
function formatLeaf(value) {
  if (isMapping(value)) return "{}";
  if (Array.isArray(value)) return "[]";
  return formatScalar(value);
}

function formatScalar(value) {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new YamlError(`${value} cannot be written as YAML.`);
    return String(value);
  }
  return quote(String(value));
}

function quote(text) {
  if (text.includes("\n") || CONTROL_CHARS.test(text)) return doubleQuote(text);

  const ambiguous =
    text === "" ||
    RESERVED_PLAIN.test(text) ||
    NUMBER_LIKE.test(text) ||
    UNSAFE_FIRST.test(text) ||
    UNSAFE_INNER.test(text) ||
    /\s$/.test(text);

  return ambiguous ? `'${text.replace(/'/g, "''")}'` : text;
}

function doubleQuote(text) {
  const escaped = text
    .replace(/[\\"]/g, (char) => `\\${char}`)
    .replace(ESCAPABLE, (char) => {
      if (char === "\n") return "\\n";
      if (char === "\t") return "\\t";
      if (char === "\r") return "\\r";
      return `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`;
    });
  return `"${escaped}"`;
}

// --- parse -------------------------------------------------------------------

/**
 * Parse the supported YAML subset.
 *
 * @param {string} text
 * @returns {*} Plain objects, arrays, strings, numbers, booleans and nulls.
 * @throws {YamlError} On malformed input, or on a construct this module refuses.
 */
export function parseYaml(text) {
  const state = { lines: tokenise(text), index: 0, depth: 0 };

  skipBlank(state);
  if (state.lines[state.index]?.content === "---") state.index += 1;

  skipBlank(state);
  if (state.index >= state.lines.length) return null;

  const value = parseNode(state, state.lines[state.index].indent);

  skipBlank(state);
  const trailing = state.lines[state.index];
  if (trailing) {
    const multiDocument = trailing.content === "---" || trailing.content === "...";
    throw new YamlError(
      multiDocument ? "A file must contain exactly one YAML document." : "Unexpected content.",
      trailing.number,
    );
  }
  return value;
}

function tokenise(text) {
  return text
    .replace(BOM_PREFIX, "")
    .split(/\r\n|\r|\n/)
    .map((line, offset) => {
      if (/^ *\t/.test(line)) {
        throw new YamlError("Tabs cannot be used for indentation in YAML.", offset + 1);
      }
      const indent = line.length - line.trimStart().length;
      const content = line.slice(indent).trimEnd();
      return {
        number: offset + 1,
        indent,
        content,
        blank: content === "" || content.startsWith("#"),
        raw: line,
      };
    });
}

function skipBlank(state) {
  while (state.index < state.lines.length && state.lines[state.index].blank) state.index += 1;
}

function parseNode(state, indent) {
  state.depth += 1;
  if (state.depth > MAX_DEPTH) {
    throw new YamlError(`Nesting deeper than ${MAX_DEPTH} levels.`, state.lines[state.index]?.number);
  }
  try {
    skipBlank(state);
    const line = state.lines[state.index];
    if (!line || line.indent < indent) return null;
    return isSequenceEntry(line.content)
      ? parseSequence(state, line.indent)
      : parseMapping(state, line.indent);
  } finally {
    state.depth -= 1;
  }
}

function parseMapping(state, indent) {
  const map = {};

  for (;;) {
    skipBlank(state);
    const line = state.lines[state.index];
    if (!line || line.indent !== indent || isSequenceEntry(line.content)) break;

    if (line.content === "---" || line.content === "...") {
      throw new YamlError("A file must contain exactly one YAML document.", line.number);
    }

    const entry = splitKey(line.content, line.number);
    if (!entry) throw new YamlError("Expected `key: value`.", line.number);
    if (entry.key === "<<") throw new YamlError("Merge keys (`<<`) are not supported.", line.number);
    if (Object.prototype.hasOwnProperty.call(map, entry.key)) {
      throw new YamlError(`Duplicate key "${entry.key}".`, line.number);
    }

    state.index += 1;
    map[entry.key] = readValue(state, line, entry.rest, indent);
  }

  return map;
}

function parseSequence(state, indent) {
  const list = [];

  for (;;) {
    skipBlank(state);
    const line = state.lines[state.index];
    if (!line || line.indent !== indent || !isSequenceEntry(line.content)) break;

    const rest = line.content === "-" ? "" : line.content.slice(2);
    if (stripComment(rest, line.number) === "") {
      state.index += 1;
      list.push(parseChildBlock(state, indent));
      continue;
    }

    // Compact form (`- name: x`, `- - y`): re-read the line as though the item
    // began in its own column, which is what YAML says it does.
    const column = indent + 2 + (rest.length - rest.trimStart().length);
    const content = rest.trimStart();
    state.lines[state.index] = { ...line, indent: column, content };

    if (isSequenceEntry(content) || splitKey(content, line.number)) {
      list.push(parseNode(state, column));
    } else {
      state.index += 1;
      list.push(parseInline(state, line, content, column));
    }
  }

  return list;
}

/** The value of a `key:` line: inline, a block scalar, or the block below it. */
function readValue(state, line, rest, indent) {
  if (rest === "") return parseChildBlock(state, indent);

  const header = rest.match(/^([|>])([-+]?)(\d*) *(?:#.*)?$/);
  if (header) {
    if (header[3]) {
      throw new YamlError("Block scalar indentation indicators are not supported.", line.number);
    }
    return readBlockScalar(state, indent, header[1], header[2]);
  }

  return parseInline(state, line, rest, indent);
}

function parseChildBlock(state, parentIndent) {
  skipBlank(state);
  const next = state.lines[state.index];
  if (!next) return null;
  if (next.indent > parentIndent) return parseNode(state, next.indent);
  // A sequence may sit at its key's own column, which is how `safe_dump` writes
  // it; anything shallower means the key simply has no value.
  if (next.indent === parentIndent && isSequenceEntry(next.content)) {
    return parseSequence(state, parentIndent);
  }
  return null;
}

function parseInline(state, line, rest, indent) {
  rejectUnsupportedPrefix(rest, line.number);

  if (rest.startsWith("[") || rest.startsWith("{")) return parseFlow(rest, line.number);

  if (rest.startsWith("'") || rest.startsWith('"')) {
    const scalar = readQuoted(rest, line.number);
    if (stripComment(rest.slice(scalar.end), line.number) !== "") {
      throw new YamlError("Unexpected content after a quoted value.", line.number);
    }
    return scalar.value;
  }

  // A plain scalar continues on any deeper line that follows it, folded with a
  // single space — `safe_dump` wraps a long default question exactly this way.
  const parts = [stripComment(rest, line.number)];
  for (;;) {
    const next = state.lines[state.index];
    if (!next || next.blank || next.indent <= indent || isSequenceEntry(next.content)) break;
    parts.push(stripComment(next.content, next.number));
    state.index += 1;
  }
  return resolveScalar(parts.join(" ").trim());
}

/**
 * `|` keeps newlines, `>` folds them into spaces. Chomping: `-` strips the
 * trailing newline, anything else clips to exactly one.
 */
function readBlockScalar(state, parentIndent, style, chomping) {
  const collected = [];
  let blockIndent = null;

  while (state.index < state.lines.length) {
    const line = state.lines[state.index];
    const isBlank = line.content === "";
    if (!isBlank && line.indent <= parentIndent) break;
    if (blockIndent === null && !isBlank) blockIndent = line.indent;
    collected.push(isBlank ? "" : line.raw.slice(blockIndent));
    state.index += 1;
  }

  while (collected.length && collected.at(-1) === "") collected.pop();
  if (!collected.length) return "";

  const body =
    style === "|"
      ? collected.join("\n")
      : collected.reduce((text, item, position) => {
          if (position === 0) return item;
          // A blank line inside a folded scalar is a paragraph break.
          const paragraph = item === "" || collected[position - 1] === "";
          return `${text}${paragraph ? "\n" : " "}${item}`;
        }, "");

  return chomping === "-" ? body : `${body}\n`;
}

function rejectUnsupportedPrefix(text, lineNumber) {
  const refusals = {
    "&": "Anchors (`&name`) are not supported.",
    "*": "Aliases (`*name`) are not supported.",
    "!": "Tags (`!name`) are not supported.",
    "?": "Explicit keys (`? key`) are not supported.",
  };
  const message = refusals[text[0]];
  if (message) throw new YamlError(message, lineNumber);
}

function isSequenceEntry(content) {
  return content === "-" || content.startsWith("- ");
}

/**
 * Split `key: rest`, or return null when the line is not a mapping entry. The
 * key may be quoted; an unquoted colon has to be followed by a space or end the
 * line, which is what keeps `10:30` and `http://example.org` out of key
 * position.
 */
function splitKey(content, lineNumber) {
  if (content.startsWith("[") || content.startsWith("{")) return null;

  if (content.startsWith("'") || content.startsWith('"')) {
    const scalar = readQuoted(content, lineNumber);
    const after = content.slice(scalar.end).trim();
    if (!after.startsWith(":")) return null;
    return { key: String(scalar.value), rest: after.slice(1).trim() };
  }

  for (let position = 0; position < content.length; position += 1) {
    const char = content[position];
    if (char === "#") return null;
    if (char !== ":") continue;
    if (position + 1 < content.length && content[position + 1] !== " ") continue;

    const key = content.slice(0, position).trim();
    if (!key) return null;
    return { key: String(resolveScalar(key)), rest: content.slice(position + 1).trim() };
  }
  return null;
}

/**
 * Read a quoted scalar at the start of `text`.
 * @returns {{value: string, end: number}} `end` indexes just past the closing
 *   quote, so a caller can see what follows without guessing.
 */
function readQuoted(text, lineNumber) {
  const quoteChar = text[0];
  let value = "";

  for (let position = 1; position < text.length; position += 1) {
    const char = text[position];

    if (quoteChar === "'") {
      if (char !== "'") {
        value += char;
      } else if (text[position + 1] === "'") {
        value += "'";
        position += 1;
      } else {
        return { value, end: position + 1 };
      }
      continue;
    }

    if (char === "\\") {
      const escape = text[position + 1];
      if (escape === "u") {
        const hex = text.slice(position + 2, position + 6);
        if (!/^[0-9a-fA-F]{4}$/.test(hex)) throw new YamlError("Malformed \\u escape.", lineNumber);
        value += String.fromCharCode(Number.parseInt(hex, 16));
        position += 5;
        continue;
      }
      const simple = SIMPLE_ESCAPES[escape];
      if (simple === undefined) throw new YamlError(`Unknown escape \\${escape}.`, lineNumber);
      value += simple;
      position += 1;
      continue;
    }

    if (char === '"') return { value, end: position + 1 };
    value += char;
  }

  throw new YamlError("Unterminated quoted string.", lineNumber);
}

/**
 * Remove a trailing `# comment`, leaving a `#` inside a quoted scalar alone.
 *
 * Only a quote in the *first* column opens a quoted scalar. A quote further in
 * is ordinary text — `label: it's fine` is a legal plain scalar, and treating
 * that apostrophe as an opening quote is how a naive scan reports an
 * unterminated string on valid input.
 */
function stripComment(text, lineNumber) {
  let position = 0;
  if (text.startsWith("'") || text.startsWith('"')) {
    position = readQuoted(text, lineNumber).end;
  }

  for (; position < text.length; position += 1) {
    const isComment = text[position] === "#" && (position === 0 || /\s/.test(text[position - 1]));
    if (isComment) return text.slice(0, position).trim();
  }
  return text.trim();
}

// --- flow collections --------------------------------------------------------

function parseFlow(text, lineNumber) {
  const state = { text, index: 0, line: lineNumber, depth: 0 };
  const value = flowNode(state);

  skipFlowSpace(state);
  if (state.index < text.length && text[state.index] !== "#") {
    throw new YamlError("Unexpected content after a flow collection.", lineNumber);
  }
  return value;
}

function flowNode(state) {
  state.depth += 1;
  if (state.depth > MAX_DEPTH) throw new YamlError("Flow collection nested too deeply.", state.line);
  try {
    skipFlowSpace(state);
    const char = state.text[state.index];
    if (char === "[") return flowSequence(state);
    if (char === "{") return flowMapping(state);
    return flowScalar(state);
  } finally {
    state.depth -= 1;
  }
}

function flowSequence(state) {
  state.index += 1; // "["
  const list = [];

  for (;;) {
    skipFlowSpace(state);
    if (state.text[state.index] === "]") {
      state.index += 1;
      return list;
    }
    if (state.index >= state.text.length) throw new YamlError("Unclosed `[`.", state.line);

    list.push(flowNode(state));
    skipFlowSpace(state);
    if (state.text[state.index] === ",") state.index += 1;
  }
}

function flowMapping(state) {
  state.index += 1; // "{"
  const map = {};

  for (;;) {
    skipFlowSpace(state);
    if (state.text[state.index] === "}") {
      state.index += 1;
      return map;
    }
    if (state.index >= state.text.length) throw new YamlError("Unclosed `{`.", state.line);

    const key = flowScalar(state);
    skipFlowSpace(state);
    if (state.text[state.index] !== ":") {
      throw new YamlError("Expected `:` in a flow mapping.", state.line);
    }
    state.index += 1;
    map[String(key)] = flowNode(state);

    skipFlowSpace(state);
    if (state.text[state.index] === ",") state.index += 1;
  }
}

function flowScalar(state) {
  skipFlowSpace(state);
  rejectUnsupportedPrefix(state.text.slice(state.index), state.line);

  const char = state.text[state.index];
  if (char === "'" || char === '"') {
    const scalar = readQuoted(state.text.slice(state.index), state.line);
    state.index += scalar.end;
    return scalar.value;
  }

  let end = state.index;
  while (end < state.text.length && !",[]{}:".includes(state.text[end])) end += 1;
  const raw = state.text.slice(state.index, end).trim();
  state.index = end;
  return resolveScalar(raw);
}

function skipFlowSpace(state) {
  while (state.index < state.text.length && /\s/.test(state.text[state.index])) state.index += 1;
}

// --- scalars -----------------------------------------------------------------

function resolveScalar(text) {
  if (text === "" || NULL_SCALAR.test(text)) return null;
  if (BOOL_TRUE.test(text)) return true;
  if (BOOL_FALSE.test(text)) return false;
  if (INTEGER.test(text)) return Number.parseInt(text, 10);
  if (FLOAT.test(text)) return Number.parseFloat(text);
  return text;
}

function isMapping(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function pad(indent) {
  return " ".repeat(indent);
}
