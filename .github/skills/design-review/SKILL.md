---
name: design-review
description: Review UI implementations for Microsoft Foundry (formerly Azure AI Studio) against Microsoft Foundry design quality standards. Evaluates using four pillars - frictionless insight-to-action, progressive clarity, quality craft, and trustworthy building. Use for PR reviews, design reviews, accessibility checks, and UX quality assessments in the Foundry application. Ensures Fluent UI compliance and Storybook component usage.
---

# Design Review - Microsoft Foundry

Evaluate UI implementations for **Microsoft Foundry** against Microsoft design quality standards. Apply these four pillars to all Foundry application work using Microsoft Fluent patterns and Storybook components.

## Foundry Context

Microsoft Foundry is a comprehensive platform for AI application development, including:
- Model catalog, deployment, and testing (Playground)
- Agent building and orchestration
- Dataset management and evaluation
- Tracing and observability
- Project and team collaboration

This skill applies to all Foundry surfaces: project views, model catalog, playground, evaluation flows, deployment wizards, and settings.

## Review Process

1. **Identify user task**: What is the user trying to accomplish in Foundry?
2. **Identify scope**: Component, feature, or complete flow
3. **Gather context**: Screenshots, code, design files, or live implementation
4. **Evaluate each pillar** using criteria below
5. **Score and prioritize** issues by severity (blocking/major/minor)
6. **Provide recommendations** with Fluent pattern examples

## Core Principles

**Task completion:**
- Users must complete their core AI development task with minimum clicks/interactions
- Every screen should answer: "What can I do here?" and "What happens next?"
- Common Foundry tasks: Deploy model, test in playground, create evaluation, view traces, manage datasets

**Action hierarchy:**
- Clutter is bad—limit primary actions to 1-2 per view
- Use Fluent primary/secondary/tertiary button hierarchy
- Progressive disclosure for additional options
- Foundry pattern: Primary action in top-right (Deploy, Run, Save), contextual actions in overflow

**Onboarding:**
- Explain what the feature does when introducing it (especially for AI concepts)
- First-time experience should guide without blocking
- Smart defaults over configuration (e.g., recommended models, default parameters)
- Foundry examples: Model recommendations, pre-configured templates, example prompts

**Navigation:**
- Clear entry and exit points for every experience
- Back/cancel always available and obvious
- Breadcrumbs or context indicators for deep flows
- Foundry navigation: Left sidebar for project structure, top nav for context switching, breadcrumbs for hierarchical navigation

## Quality Pillars

### 1. Frictionless Insight to Action

Design for momentum. Signal, insight, and next step belong in one view. Users complete their task efficiently.

**Evaluate:**
- **Task completion**: Identify the user's goal—can they complete it in 3 or fewer interactions? Exceeding 3 interactions should be avoided unless necessary for complex tasks.
- **Action clarity**: Primary action (Fluent Button variant="primary") is obvious and singular
- **Next steps visible**: Every state shows what to do next (success, error, loading)
- **No clutter**: Limit to 1-2 primary actions; use CommandBar or overflow menu for secondary
- **Navigation**: Clear path back and forward through the experience

**Fluent patterns:**
- Primary button (1 per view), Default button (supporting actions), Subtle button (tertiary)
- CommandBar for grouped actions (top of content areas)
- SplitButton for primary + related options
- Stack/Card for organized content hierarchy
- **Foundry-specific**: Split view with nav sidebar + content area, tabbed sections for related content, card-based galleries for models/deployments/evaluations

**Foundry examples:**
- 🟢 Deploy flow: Model catalog → Select model → Configure (defaults) → Deploy → Playground link
- 🟢 Playground: Chat interface with clear "Run" button, model switcher in header, prompt examples shown
- ⚫ Evaluation setup requiring >5 clicks through multiple panels without clear progress

**Red flags:** 
- Dead ends (no next action after task completion)
- Excessive clicks (>3 steps for primary Foundry workflows like deploy or test)
- Buried primary actions (below fold, in menus, or visually de-emphasized)
- Modal chains (multiple sequential modals)
- Multiple competing primary buttons
- No clear way to exit or go back
- **Foundry-specific**: Losing context when navigating between project areas, unclear relationship between playground and deployment, missing breadcrumbs in deep hierarchies

### 2. Progressive Clarity

Keep the default path simple. Reveal depth only when needed. Explain features on introduction.

**Evaluate:**
- **Onboarding**: Feature purpose explained on first encounter
- **Smart defaults**: No unnecessary upfront configuration—users can proceed immediately
- **Documentation-free**: Happy path works without reading docs
- **Progressive disclosure**: Advanced options collapsed, in panels, or in settings
- **Choice reduction**: Show 3-5 options by default; use "Show more" for additional choices

**Fluent patterns:**
- Accordion for collapsible sections
- Pivot/Tab for switching between views without leaving context
- Panel (side drawer) for advanced settings
- Tooltip/InfoButton for contextual help
- Teaching callouts for first-time feature introduction
- Dropdown with grouped/categorized options
- **Foundry-specific**: Model comparison cards (show top 3-5, expand for all), parameter groups in collapsible sections, inline help for AI concepts (temperature, top-p, etc.)

**Foundry examples:**
- 🟢 Model catalog: "Recommended for you" section with 3-5 models, "Show all 100+" in accordion
- 🟢 Deployment: Smart defaults for instance type, scale, timeout; advanced in collapsed "Advanced settings"
- 🟢 Evaluation: Explains what evaluation does with example, shows pre-built evaluators first
- ⚫ Forcing users to understand temperature/top-p before first playground interaction
- ⚫ Model list showing all 100+ models in unsorted flat list

**Red flags:** 
- Configuration overload (form with >5 required fields before starting)
- Required reading (can't proceed without documentation)
- Hidden essential features (buried in menus without discoverability)
- Flat lists with >10 items (no grouping/filtering)
- Features without explanation (user asks "what does this do?")
- **Foundry-specific**: Model catalog showing all 100+ models unsorted, deployment wizard requiring deep LLM knowledge upfront, evaluation metrics without explanation, AI jargon without definitions

### 3. Quality is Craft

Typography, density, spacing, and microcopy shape outcomes. Use Storybook components and Fluent patterns.

**Evaluate:**
- **Component compliance**: Uses Fluent UI React v9 components from Storybook
- **Accessibility**: Grade C minimum (acceptable), Grade B ideal (target)
- **Multiple modalities**: Works with keyboard, mouse, touch, screen reader, and voice
- **Responsive design**: Reflow tested at 320px (mobile), 1024px (tablet), 1920px (desktop)
- **Theme support**: Tested in light, dark, and high contrast modes
- **Microcopy**: Clear, concise, action-oriented labels

**Accessibility Grades:**
- **Grade A**: WCAG 2.1 AAA + enhanced Fluent patterns (aspirational for critical flows)
- **Grade B**: WCAG 2.1 AA compliance (ideal—actively working toward this)
- **Grade C**: WCAG 2.1 A compliance (minimum acceptable bar)
- **Grade F**: Non-compliant (blocking issue—must fix)

**Grade C minimum requirements:**
- Keyboard navigation: Core interactive elements accessible via keyboard
- Focus indicators: Basic visible focus state
- Screen reader: Basic semantic structure and labels
- Color contrast: 3:1 minimum for large text and UI components

**Grade B ideal (target this):**
- Keyboard navigation: All interactive elements focusable, logical tab order
- Focus indicators: Clear, high-visibility focus state (Fluent provides by default)
- Screen reader: Proper ARIA labels, roles, live regions, and announcements
- Color contrast: 4.5:1 for text, 3:1 for UI components
- Text resize: Readable at 200% zoom without horizontal scroll
- Error identification: Errors clearly announced and programmatically linked to fields

**Fluent Storybook components** (always prefer over custom):
- Layout: Stack, Card, Divider
- Input: Input, Dropdown, Combobox, Checkbox, Radio, Switch, Slider
- Buttons: Button, SplitButton, MenuButton, ToggleButton
- Navigation: TabList, Breadcrumb, Menu, CommandBar
- Feedback: MessageBar, ProgressBar, Spinner, Dialog, Toast
- Data: Table, DataGrid, Tree, List

**Foundry-specific components:**
- Model cards with metadata (parameters, cost, latency)
- Code editor with syntax highlighting
- Trace viewer with hierarchical spans
- Evaluation results tables with metrics comparison
- Chat message list with user/assistant distinction

**Foundry examples:**
- 🟢 Uses Storybook Button with variant="primary" for main actions
- 🟢 Stack with tokens for spacing (spacingVerticalM between cards)
- 🟢 Code editor with copy Button and syntax highlighting
- 🟢 Keyboard navigation: Tab order logical, Enter/Space work, Esc closes panels
- ⚫ Custom components without accessibility (reinventing Fluent)
- ⚫ Hardcoded margins instead of design tokens
- ⚫ Dark mode text unreadable (poor contrast)

**Standards:**
- Use Fluent tokens for spacing (spacingHorizontalS, spacingVerticalM)
- Use design tokens for colors (never hardcoded hex values)
- Follow Fluent typography scale
- Test with Windows Narrator and NVDA screen readers

**Red flags:** 
- Custom components without accessibility (reinventing Fluent components)
- Broken reflow (horizontal scroll, overlapping content)
- Mode-specific bugs (dark mode text unreadable)
- Missing focus indicators or skip links
- Non-semantic HTML (div/span soup instead of proper elements)
- Inconsistent spacing or typography (not using tokens)
- **Foundry-specific**: Code snippets without copy button, model parameters without units/ranges, trace data without timestamps

### 4. Trustworthy Building

Equip developers to build with confidence. Safe by default, transparent by design.

**Evaluate:**
- **AI transparency**: AI-generated content includes required disclaimer
- **Secure defaults**: Least privilege access, safe configurations selected by default
- **Data clarity**: Provenance, policy state, and data boundaries clearly visible
- **Progressive controls**: Security and compliance options discoverable but not obstructive
- **Error transparency**: Clear error messages with actionable next steps

**Required disclaimer:** 
"AI-generated content may be incorrect" (use MessageBar or InfoLabel)

**Fluent patterns:**
- MessageBar for warnings and AI disclaimers
- InfoLabel for inline security context
- PresenceBadge for status indicators (secure/warning/error)
- Badge for policy/compliance state
- Persona for identity and access context

**Foundry examples:**
- 🟢 Playground responses: "AI-generated content may be incorrect" MessageBar shown
- 🟢 Deployment defaults: Private endpoint, managed identity, minimal permissions
- 🟢 Dataset upload: "Data stored in [region], encrypted at rest, retained for 30 days"
- 🟢 Error: "Deployment failed: Insufficient quota. Request increase via [link]"
- ⚫ Generated code shown without AI disclaimer
- ⚫ Default deployment: Public endpoint with admin keys
- ⚫ Opaque error: "Something went wrong" without context

**Red flags:** 
- Missing AI disclaimers on generated content
- Hidden security controls (buried in settings)
- Unclear data boundaries (where does data go?)
- Insecure defaults (admin access, public sharing)
- Opaque errors ("Something went wrong" without guidance)
- **Foundry-specific**: Model responses without provenance, unclear data retention policies, missing cost estimates before deployment, API keys shown in plaintext

## Pattern Examples

**🟢 Good: Frictionless (Task Completion in Foundry)**
- Deploy model: Model catalog → Select GPT-4 → Review config (smart defaults) → Deploy → "Test in playground" CTA
- User task: Deploy a model for testing (3 clicks, clear next action)
- Single primary "Deploy" Button, secondary actions in overflow Menu
- Clear breadcrumb: Projects > MyProject > Deployments > Deploy model
- Success page shows deployment details + immediate "Open playground" action

**⚫ Bad: Frictionless**
- Deploy requires: Read docs → Understand SKUs → Create config file → Validate → Fix errors → Upload → Deploy (>6 steps)
- User task unclear, no explanation of what deployment means
- Three primary buttons: "Deploy", "Configure", "Advanced" (competing attention)
- Success page is dead end with no suggested next steps
- No way to quickly test the deployment

**🟢 Good: Progressive Clarity (Foundry Onboarding)**
- Model selection: "Choose a model for your task" with explanation "Models generate text based on your prompts"
- Shows 3 recommended models in Cards: GPT-4 (Versatile), GPT-3.5 (Fast & affordable), Llama (Open source)
- Each card explains: use case, cost, latency
- "Show all 50+ models" Accordion for advanced users
- Advanced configuration collapsed: "Advanced settings (optional)"

**⚫ Bad: Progressive Clarity**
- 100+ models in flat, unsorted list without categories
- Form with 8 required fields: temperature, top_p, frequency_penalty, presence_penalty, max_tokens, stop_sequences, best_of, n
- No explanation of what each parameter does or suggested values
- Can't proceed without configuring all fields
- AI terminology without definitions

**🟢 Good: Quality Craft (Foundry Fluent Usage)**
- Uses Storybook Button with variant="primary" for "Run" in playground
- Stack with tokens: spacingVerticalL between message groups
- MessageBar for AI disclaimer: "AI-generated content may be incorrect" 
- Code editor with copy Button, syntax highlighting
- Tested with keyboard: Tab order logical, Enter submits prompt, Esc closes panels
- High contrast mode: All text readable, focus indicators visible
- Model cards use design tokens for spacing and colors

**⚫ Bad: Quality Craft**
- Custom button with inline styles, no focus indicator
- Hardcoded margins: `style={{ margin: '10px' }}`
- No keyboard support: onClick only, can't submit with Enter
- Dark mode: Gray text on black background (contrast ratio 2:1)
- Code blocks without syntax highlighting or copy functionality

**🟢 Good: Trustworthy (Foundry Transparency)**
- Playground response with MessageBar: "AI-generated content may be incorrect. Verify before use."
- Deployment defaults: Private endpoint (secure), managed identity (no keys), East US (shows region)
- PresenceBadge shows: "Deployment active" with green dot
- Data upload: "Files encrypted at rest, stored in East US, deleted after 30 days unless saved"
- Error message: "Deployment failed: Insufficient GPU quota. Request quota increase in Azure Portal → Quotas."
- Cost estimate shown before deployment: "~$0.50/hour for Standard_D4s instance"

**⚫ Bad: Trustworthy**
- AI-generated code shown without disclaimer
- Default deployment: Public endpoint with API key authentication
- Error: "Error 500: Internal server error" (no context or next steps)
- Data handling unclear: where data is stored, who has access, retention policy
- No cost visibility until after deployment
- API keys displayed in plaintext without warning

## Review Output Format

```
## Design Review: [Component/Feature Name]

### User Task
What is the user trying to accomplish in Foundry? [Brief description]
Can they complete it? [Yes/No - explain]

### Summary
[Pass/Needs Work/Blocked] - [One-line assessment]

### Pillar Assessment

| Pillar | Status | Notes |
|--------|--------|-------|
| Frictionless | 🟢/🟠/⚫ | Task completion: X clicks, navigation: clear/unclear |
| Progressive Clarity | 🟢/🟠/⚫ | Onboarding: present/missing, defaults: smart/manual |
| Quality Craft | 🟢/🟠/⚫ | Storybook: yes/no, Accessibility: Grade X |
| Trustworthy | 🟢/🟠/⚫ | AI disclaimer: yes/no, secure defaults: yes/no |

**Legend:** 🟢 Pass | 🟠 Needs attention | ⚫ Blocking issue

### Q's Design Critique
**Verdict:** [Pass / Needs work / Reach out to design for more support]

**Rationale:** [Brief explanation of the verdict based on pillar assessment]

**Criteria:**
- **Pass**: All pillars 🟢 or minor 🟠 that don't block user tasks
- **Needs work**: Multiple 🟠 or any critical workflow issues that should be addressed
- **Reach out to design for more support**: Any ⚫ blocking issues, fundamental pattern problems, or complex design challenges requiring collaboration

### Issues

**Blocking (must fix before merge):**
1. [Pillar] Issue description + Fluent component recommendation

**Major (should fix):**
1. [Pillar] Issue description + pattern suggestion

**Minor (consider for refinement):**
1. [Pillar] Issue description + optional improvement

### Recommendations
- [Fluent component or pattern to use]
- [Specific code or design change]
- [Link to Storybook example if applicable]
- [Foundry-specific pattern reference]
```

## Review Type Modifiers

Adjust focus based on review context:

**PR Review**: 
- Focus: Code implementation, Storybook component usage, accessibility in code
- Check: Proper Fluent imports, design tokens used, ARIA attributes present, Foundry data models correct

**Design Review**: 
- Focus: User flows, interaction patterns, visual hierarchy, navigation
- Check: Task completion path, action hierarchy, progressive disclosure, Foundry navigation patterns

**Accessibility Audit**: 
- Focus: Deep dive Quality Craft pillar
- Check: Keyboard testing, screen reader testing, contrast ratios, ARIA patterns
- Test with: Windows Narrator, NVDA, keyboard only, 200% zoom
- Foundry-specific: Code editor accessibility, trace viewer keyboard navigation, chat interface screen reader support

**Security Review**: 
- Focus: Deep dive Trustworthy pillar
- Check: Default permissions, data handling, AI disclaimers, error information disclosure
- Foundry-specific: API key management, deployment security, data retention, model access controls

## Quick Checklist

Before approving any Foundry UI work:

**Frictionless:**
- [ ] User task clearly identified and completable in Foundry context
- [ ] Core task requires ≤3 interactions
- [ ] Only 1-2 primary actions per view (avoid clutter)
- [ ] Every view has clear next action
- [ ] No dead ends without escape route
- [ ] Clear back/cancel navigation throughout
- [ ] Entry and exit points obvious
- [ ] Foundry navigation: Breadcrumbs for deep flows, sidebar context preserved

**Progressive Clarity:**
- [ ] Feature purpose explained on introduction (especially AI concepts)
- [ ] Works without reading documentation
- [ ] Smart defaults for 80% use cases
- [ ] Advanced options in Accordion/Panel/Settings (not prominent)
- [ ] Choice limited: 3-5 visible options, "Show more" for rest
- [ ] Foundry: Model recommendations shown, complex parameters hidden, jargon explained

**Quality Craft:**
- [ ] Uses Fluent UI React v9 Storybook components
- [ ] Design tokens used for spacing/colors (no hardcoded values)
- [ ] Accessibility Grade C minimum, Grade B ideal
- [ ] Keyboard navigation complete (all interactive elements)
- [ ] Tested in light/dark/high contrast modes
- [ ] Responsive: tested at 320px, 1024px, 1920px
- [ ] Microcopy clear and action-oriented
- [ ] Foundry: Code blocks have copy button, model cards show metadata, traces are readable

**Trustworthy:**
- [ ] AI-generated content has required disclaimer
- [ ] Secure defaults (least privilege)
- [ ] Data boundaries and provenance clear
- [ ] Error messages actionable
- [ ] Policy/compliance state visible when relevant
- [ ] Foundry: Deployment security configured, cost estimates shown, data retention clear, API keys protected
