import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import Capture, { updateRuleConcept } from './Capture';

describe('Capture page checklist compiler', () => {
  const mockCompiledTemplate = {
    id: 'tmpl_custom_01',
    name: 'Custom Checklist',
    description: 'Custom checklist description',
    disclaimer: 'For inspection purposes',
    rules: [
      {
        id: 'rule_1',
        title: 'Verify fire extinguisher is mounted',
        condition: 'Verify fire extinguisher is mounted',
        type: 'presence' as const,
        severity: 'high' as const,
        sam_prompts: ['fire extinguisher'],
        params: {},
        fix_text: 'Mount fire extinguisher',
      },
    ],
  };

  it('shows SAM concept separately from condition with "SAM concept valid" label and never "Validated for SAM 3.1"', () => {
    const html = renderToString(
      <MemoryRouter initialEntries={['/audits/new/custom']}>
        <Capture initialCompiledTemplate={mockCompiledTemplate} />
      </MemoryRouter>
    );

    // Separately shows Condition and SAM Concept
    expect(html).toContain('Condition:');
    expect(html).toContain('Verify fire extinguisher is mounted');
    expect(html).toContain('SAM Concept:');
    expect(html).toContain('value="fire extinguisher"');

    // Label must say "SAM concept valid"
    expect(html).toContain('SAM concept valid');

    // Must NEVER say "Validated for SAM 3.1"
    expect(html).not.toContain('Validated for SAM 3.1');
  });

  it('shows warning "Compound or negated statement: split it into separate rules or confirm" and requires confirmation', () => {
    const htmlUnconfirmed = renderToString(
      <MemoryRouter initialEntries={['/audits/new/custom']}>
        <Capture
          initialCompiledTemplate={mockCompiledTemplate}
          initialCompileWarnings={['Compound or negated statement: split it into separate rules or confirm']}
          initialHasConfirmedCompound={false}
        />
      </MemoryRouter>
    );

    // Warning is rendered
    expect(htmlUnconfirmed).toContain('Compound or negated statement: split it into separate rules or confirm');
    expect(htmlUnconfirmed).toContain('Confirm Statement');
    expect(htmlUnconfirmed).toContain('Compound or negated statement requires confirmation or editing before saving');

    const htmlConfirmed = renderToString(
      <MemoryRouter initialEntries={['/audits/new/custom']}>
        <Capture
          initialCompiledTemplate={mockCompiledTemplate}
          initialCompileWarnings={['Compound or negated statement: split it into separate rules or confirm']}
          initialHasConfirmedCompound={true}
        />
      </MemoryRouter>
    );

    expect(htmlConfirmed).toContain('Statement Confirmed');
    expect(htmlConfirmed).toContain('Statement confirmed by user');
  });

  it('renders inline concept validation error when concept contains conjunction or negation', () => {
    const html = renderToString(
      <MemoryRouter initialEntries={['/audits/new/custom']}>
        <Capture
          initialCompileErrors={[
            "Rule 'rule_1': concept 'boxes and pallets' contains conjunction ('and'/'or'). Templates must use plain noun phrases only.",
          ]}
        />
      </MemoryRouter>
    );

    expect(html).toContain('Concept Validation Failed:');
    expect(html).toContain('boxes and pallets');
    expect(html).toContain('conjunction');
  });

  it('edits concept field directly: rejects conjunction, negation, and blocks saving with inline error', () => {
    // 1. Direct edit with conjunction ("and" / "or")
    const editedConjunction = updateRuleConcept(
      mockCompiledTemplate,
      'rule_1',
      'fire extinguisher and emergency sign'
    );
    expect(editedConjunction.error).not.toBeNull();
    expect(editedConjunction.error).toContain("contains conjunction ('and'/'or')");
    expect(editedConjunction.updatedTemplate.rules[0].sam_prompts).toEqual([
      'fire extinguisher and emergency sign',
    ]);

    // Render with conjunction edited concept
    const htmlConjunction = renderToString(
      <MemoryRouter initialEntries={['/audits/new/custom']}>
        <Capture initialCompiledTemplate={editedConjunction.updatedTemplate} />
      </MemoryRouter>
    );

    // Inline error must appear under the concept field
    expect(htmlConjunction).toContain('contains conjunction');
    expect(htmlConjunction).not.toContain('SAM concept valid');
    expect(htmlConjunction).toContain('SAM concept contains invalid words (conjunction or negation): must be a plain noun phrase');
    // Button must be disabled
    expect(htmlConjunction).toContain('disabled=""');

    // 2. Direct edit with negation ("not", "unblocked")
    const editedNegation = updateRuleConcept(
      mockCompiledTemplate,
      'rule_1',
      'not blocked pathway'
    );
    expect(editedNegation.error).not.toBeNull();
    expect(editedNegation.error).toContain('contains negation');

    const htmlNegation = renderToString(
      <MemoryRouter initialEntries={['/audits/new/custom']}>
        <Capture initialCompiledTemplate={editedNegation.updatedTemplate} />
      </MemoryRouter>
    );
    expect(htmlNegation).toContain('contains negation');
    expect(htmlNegation).not.toContain('SAM concept valid');

    // 3. Direct edit back to valid plain noun phrase
    const editedValid = updateRuleConcept(
      mockCompiledTemplate,
      'rule_1',
      'emergency exit door'
    );
    expect(editedValid.error).toBeNull();
    expect(editedValid.updatedTemplate.rules[0].sam_prompts).toEqual(['emergency exit door']);

    const htmlValid = renderToString(
      <MemoryRouter initialEntries={['/audits/new/custom']}>
        <Capture initialCompiledTemplate={editedValid.updatedTemplate} />
      </MemoryRouter>
    );
    expect(htmlValid).toContain('SAM concept valid');
    expect(htmlValid).not.toContain('contains conjunction');
    expect(htmlValid).not.toContain('contains negation');
  });
});
