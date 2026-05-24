# Reference images

This folder holds **reference images** the product owner has shared on PRs,
issues, or discussions. They are committed into the repo (rather than left
as ephemeral GitHub attachment URLs) so that future readers and agents can
see exactly what was described, without depending on external storage.

## Convention

- One PNG/JPG per image. Lowercase, hyphen-separated, descriptive filename
  (e.g. `berlin-warehouse-reference.png`).
- Embed it in `PRODUCT.md` (and any other doc that benefits) with a short
  caption explaining what it shows and which comment / PR it came from.
- Keep the original GitHub attachment URL as a fallback in the caption so
  readers can trace provenance.

## Adding a new image

1. Drop the file into this folder.
2. Add a row to the **§6 Reference images** table in
   [`../../PRODUCT.md`](../../PRODUCT.md).
3. Embed it (or link to it) wherever it is described in `PRODUCT.md`.

## Note on sandboxed agents

GitHub user-attachment URLs (`https://github.com/user-attachments/...`)
redirect to S3, which is blocked from sandboxed CI / agent environments.
If a sandboxed agent needs to add a new reference image and cannot download
it, it should:

1. Add the markdown reference + caption to `PRODUCT.md` using the GitHub
   attachment URL (so the doc still renders on GitHub).
2. Note in the PR / reply that the local PNG could not be committed because
   of the sandbox egress policy, and ask the owner to drop the binary into
   this folder.
