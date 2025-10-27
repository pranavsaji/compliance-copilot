# Compliance Copilot (MVP, runnable)

## Quick start
```bash
# 1) Prepare env
cp .env.example .env

# 2) Build + run
cd docker
docker compose up -d --build

# 3) Initialize Weaviate classes (one-time)
docker compose exec api python -m app.scripts.bootstrap_classes

# 4) Ingest sample data
docker compose exec api python -m app.scripts.ingest_policies
docker compose exec api python -m app.scripts.ingest_evidence

# 5) Call the API
curl -s http://localhost:8080/healthz
curl -s -X POST http://localhost:8080/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"How do we satisfy SOC2 CC6.2?", "frameworks": ["SOC2"], "limit": 6}'


Command to run:
python -m app.ui.gradio_app



1) Upload the SOC 2 catalog (ground truth)

Upload PDFs →

PDFs: SOC 2 (AICPA Trust Services Criteria).pdf

Doc type: STANDARD

Target chunk size (chars): 400

Overlap (chars): 100

Optional title hint: SOC 2 AICPA Trust Services Criteria

Standard hint (fallback): SOC 2 TSC

Force the Standard hint for ALL files: ✅ ON

Manual tags: CC6.1, CC6.2, CC6.3, CC6.4, access control, MFA, deprovisioning

Additional metadata (JSON):

{
  "publisher": "AICPA",
  "version": "TSC (latest)",
  "source_type": "standard"
}


Click Ingest PDFs.

2) Upload your company policy (evidence)

Upload PDFs →

PDFs: Access Control Policy.pdf

Doc type: COMPANY

Target chunk size (chars): 400

Overlap (chars): 100

Optional title hint: Access Control Policy

Standard hint (fallback): (you can leave blank) or set SOC 2 TSC

Force the Standard hint for ALL files: ❌ OFF

Manual tags: CC6.1, CC6.2, access provisioning, deprovisioning, privileged access, MFA

Additional metadata (JSON):

{
  "owner": "Security",
  "policy_id": "AC-Policy-2024",
  "effective_date": "2024-01-01",
  "system": "Okta"
}


Click Ingest PDFs.

Tip: you can repeat step 2 for other company docs (e.g., “Change Management Policy”, “Contingency Planning Policy”) with Doc type = COMPANY. Leave Standard hint blank unless the doc explicitly maps to SOC 2; they’ll still show up as “company evidence” when you toggle that in Ask.

3) Ask good validation questions
A. Standard-only (confirm the catalog is in)

Ask →

Question:
Which SOC 2 criteria relate to least privilege? Provide short narratives and cite the catalog.

Standard: SOC 2 TSC

Restrict to selected Standard: ✅ ON

Include company evidence: ❌ OFF

Tags: CC6.1, CC6.2, least privilege

Result limit: 6

Expected: Only SOC 2 chunks (no company citations).

B. Mixed (map company evidence to SOC 2)

Ask →

Question:
Assess our coverage for CC6.1–CC6.2 (user registration/authorization and removal). Cite the SOC 2 requirement and our Access Control Policy evidence.

Standard: SOC 2 TSC

Restrict to selected Standard: ✅ ON

Include company evidence: ✅ ON

Tags: CC6.1, CC6.2, access provisioning, deprovisioning

Result limit: 8

Expected: SOC 2 catalog sections + company policy chunks, side-by-side with gaps called out if your policy doesn’t address parts of CC6.1/CC6.2.

C. Company-only summary (ensure company is used)

Ask →

Question:
From our Access Control Policy, summarize the joiner/mover/leaver process and control owners. Cite company evidence only.

Standard: (Any) (or keep SOC 2 TSC but this question is about your doc)

Restrict to selected Standard: ❌ OFF (to avoid filtering out company chunks with no standard tag)

Include company evidence: ✅ ON

Tags: provisioning, deprovisioning, least privilege, review

Result limit: 6

Expected: Only company policy citations.

D. Negative control (prove restriction works)

Ask →

Question:
Map our MFA controls to PCI DSS 4.0 requirements.

Standard: PCI DSS v4.0.1

Restrict to selected Standard: ✅ ON

Include company evidence: ✅ ON (ok to leave ON — company chunks without PCI standard should still appear as “company evidence”, but no PCI standard citations unless you’ve uploaded PCI)

Tags: MFA, 8.4, strong authentication

Result limit: 6

Expected: If you didn’t upload PCI, you should get no PCI catalog citations and a clear note that standard evidence for PCI wasn’t found (but it may still reference company policy if relevant).

Quick troubleshooting checklist

In Admin → Show standards snapshot, verify you see something like:
('SOC 2 TSC','STANDARD'): 63 and ('SOC 2 TSC','COMPANY'): <some number> after uploads.

In Ask, if you’re not seeing company references when you expect them:

Ensure Include company evidence is ✅ ON.

If Restrict is ✅ ON and your company chunks don’t carry a standard in metadata, they’ll still be included (by design), but standard chunks will be limited to the selected standard.

Use Tags liberally to bias retrieval (e.g., CC6.1, CC6.2, MFA, privileged access).



OR

What to set in the UI (quick checklist)

When uploading the SOC 2 catalog (standard/ground truth):

Doc type: STANDARD

Standard hint (fallback): SOC 2 TSC

Force the Standard hint: ✅ (on)

Manual tags (optional): CC6.1, CC6.2, least privilege, MFA

Split within page when long: ✅ (on)

Persist after ingest: ✅ (on)

When uploading your company policy (e.g., Access Control Policy):

Doc type: COMPANY

Standard hint (fallback): SOC 2 TSC (keeps cross-mapping easy)

Force the Standard hint: (optional, usually leave off; it will still pick up SOC 2 controls via text)

Manual tags: CC6.1, CC6.2, access provisioning, deprovisioning, privileged access, MFA

Split within page when long: ✅ (on)

Persist after ingest: ✅ (on)

When asking questions:

Standard: SOC 2 TSC

Restrict to selected Standard: ✅

Include company evidence: ✅

(Optional) Require company evidence (fail-fast): ✅ if you want a hard nudge to upload missing artifacts.


Questions to ask:
Quote the SOC 2 catalog text for CC6.1 and CC6.2 and map to our Access Control Policy sections. Use bullets: Requirement → Evidence → Gap. Cite SOC 2 chunks that contain the CC6.1/CC6.2 definitions (not privacy criteria). Cite our policy chunks too.