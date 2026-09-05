# Dashboard visual regression testing

The dashboard screenshot suite protects the desktop and mobile glass UI against accidental visual regressions. It uses deterministic API data, a fixed clock, local chart content, reduced motion, and a pinned Chromium runtime.

## Coverage

- Desktop Desk in night and day themes
- Desktop Review workspace and Pro Console
- Mobile Desk in night and day themes
- Mobile Trade and Review workspaces

The reference images live under `bot/tests/visual/__screenshots__/chromium/` and should be reviewed like source code.

## Run the comparison

Install the JavaScript dependency once, then use the same container image as CI:

```bash
npm ci
docker run --rm --init --ipc=host \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD:/work" \
  --workdir /work \
  mcr.microsoft.com/playwright:v1.62.0-noble \
  npm run test:visual
```

On a failure, inspect `playwright-report/` and `test-results/playwright/`. CI uploads both directories as a workflow artifact.

## Accept an intentional visual change

Generate new reference images only after reviewing the dashboard change in the pinned environment:

```bash
docker run --rm --init --ipc=host \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD:/work" \
  --workdir /work \
  mcr.microsoft.com/playwright:v1.62.0-noble \
  npm run test:visual:update
```

Review the changed images, rerun the normal comparison, and commit the approved baselines with the UI change. Do not update baselines simply to make an unexplained failure pass.
