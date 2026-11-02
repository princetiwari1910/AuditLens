export const FORBIDDEN_CONJUNCTION_PATTERN = /\b(and|or)\b/i;

export const FORBIDDEN_NEGATION_PATTERNS = [
  /\b(not|no|neither|nor|unblocked|without|never)\b/i,
  /\bnot\s+blocked\b/i,
  /\bnot\s+obstructed\b/i,
];

export const FORBIDDEN_SPATIAL_PATTERNS = [
  /\bon\s+(the\s+)?(left|right|top|bottom|floor|ground|wall)\b/i,
  /\bon\s+floor\b/i,
  /\bto\s+the\s+(left|right)\b/i,
  /\bin\s+the\s+(middle|center|background|foreground)\b/i,
  /\b(near|next\s+to|behind|in\s+front\s+of|beside|under|above|below)\b/i,
  /\b(blocking|obstructing|blocked|obstructed|clear\s+of\s+obstacles)\b/i,
  /\b(left|right|middle|center|background|foreground)\b/i,
];

export function validateConceptPrompt(prompt: string, ruleId?: string): string | null {
  const prefix = ruleId ? `Rule '${ruleId}': ` : '';
  if (!prompt || typeof prompt !== 'string' || !prompt.trim()) {
    return `${prefix}concept prompt must be a non-empty string.`;
  }

  const cleaned = prompt.trim();

  if (cleaned.includes(',')) {
    return `${prefix}concept '${cleaned}' contains commas. SAM requires a single plain noun phrase per prompt (no comma-separated lists).`;
  }

  if (FORBIDDEN_CONJUNCTION_PATTERN.test(cleaned)) {
    return `${prefix}concept '${cleaned}' contains conjunction ('and'/'or'). Templates must use plain noun phrases only.`;
  }

  for (const pattern of FORBIDDEN_NEGATION_PATTERNS) {
    if (pattern.test(cleaned)) {
      return `${prefix}concept '${cleaned}' contains negation. Templates must use plain noun phrases only. Negation logic belongs in the rule engine.`;
    }
  }

  for (const pattern of FORBIDDEN_SPATIAL_PATTERNS) {
    if (pattern.test(cleaned)) {
      return `${prefix}concept '${cleaned}' contains spatial words. Templates must use plain noun phrases only. Spatial and clearance logic belong in the rule engine.`;
    }
  }

  return null;
}
