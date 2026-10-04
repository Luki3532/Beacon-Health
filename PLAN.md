# Beacon Credential Tracker: Plan

## Summary

A tool that checks clinical staff credentials against public sources, tracks expiration dates, and alerts managers and HR before a credential lapses.

**Form:** a website with scheduled background jobs. Email is the main way managers interact with it.

## Problem

Credential verification is too manual. Managers must find, verify, track, print, and file credentials across disconnected sources.

1. **Multiple associates:** one radiology manager monitors about 60 associates by hand.
2. **Multiple portals:** different roles require searches across separate public credentialing websites.
3. **Paper-heavy evidence:** credentials are printed and placed into individual employee files.
4. **Expiration control:** the prior system surfaced upcoming expirations. The current process relies on manual tracking.

## Approach

- **Website, not a native app or a script alone.** It needs no install and works on any device. A script alone gives managers nowhere to see the whole picture or act on an alert.
- **Email-first.** Managers already read email, so the tool comes to them.
  - Each email is short and carries one next step.
  - One-click links go straight to the relevant person's page.
  - The dashboard is optional.
- **Scheduled jobs behind the scenes.**
  - A nightly job checks sources and recalculates expirations.
  - A second job sends alerts at 90, 60 and 30 days, and again at lapse.

## Constraints (contractor under NDA)

- Run in Beacon-owned infrastructure and accounts, so Beacon can keep running it after the contract ends.
- Design against fake or redacted sample data until Beacon approves access to real data.
- Confirm whether AI tools may be used with Beacon data.
- Keep real data, credentials and API keys out of project files. Use environment variables and a secrets store.
- Store minimal data: name, role, credential type, number, expiry date and evidence file. Exclude SSNs, birthdates and patient data.
- Role-based access: managers see only their own staff, and HR sees everyone.
- Log every view and change in an audit trail.
- Use official APIs and downloads where possible. Check each state board's terms before automating. Where automation is prohibited, link out to the site.
- Confirm code ownership in the contract and plan for documentation and handoff.

## Phases

### Phase 1: Discovery and guardrails

1. Confirm which roles and public sources are required, and whether the scope is radiology only or all clinical staff.
2. Confirm Beacon's login and email platform, approved hosting, and compliance requirements (HIPAA, vendor review).
3. Name the Beacon owner who will maintain it afterward.
4. Get a redacted sample of the credentialing spreadsheet.

### Phase 2: Foundation (depends on Phase 1)

1. Design the data model: staff, credentials, sources, evidence, alerts and audit log.
2. Import the roster from the spreadsheet.
3. Set up access control for managers and HR.

### Phase 3: Expiration tracking and alerts (depends on Phase 2)

1. Build a dashboard grouping credentials as OK, expiring soon or lapsed, filterable by manager or department.
2. Send alert emails at 90, 60 and 30 days and at lapse, each with a single link to the item.
3. Add an HR digest and escalation when an alert goes unanswered.

This phase fixes the biggest pain point, expiration tracking, before any lookups are automated.

### Phase 4: Verification and evidence (depends on Phase 3)

1. Run source lookups: official APIs where they exist, link-out where automation is not allowed.
2. Save a timestamped digital record of each check in place of printouts.
3. Add a "Mark renewed" action that updates the expiry date.

### Phase 5: Pilot and handoff (depends on Phase 4)

1. Pilot with the radiology manager and about 60 associates.
2. Adjust based on feedback.
3. Document the system and transfer it to the Beacon owner.

## Manager experience

1. Receive an email such as "3 credentials expiring within 30 days", listing names, credential types and dates.
2. Click through to the item page, using a signed link or single sign-on so there is no separate password.
3. See the credential, saved evidence, a "Verify now" button and a "Mark renewed" action. Most actions take one or two clicks.
4. Open the dashboard only when they want the full picture.

## Open questions

1. Does Beacon use Microsoft 365 / Entra single sign-on? If so, use it for login and send alerts through Outlook or Teams.
2. Where may the data be hosted: Beacon's own cloud or servers, or an outside vendor?
3. Should "Verify now" return an instant result? Some public sites cannot be automated, so the button may only open the right site with the name pre-filled.
4. Is the pilot radiology only, or several departments from the start?
5. Should the first version be email only, or include Teams alerts too?
6. Are there security or compliance requirements (HIPAA, vendor review, approved hosting)?

## Contact

Questions: Teresa Covarrubias Gonzalez (Beacon), 530-821-6753.
