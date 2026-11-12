# Changelog

## 0.1.0

- `aem.Client` signs in with an AEM API key (argument, `AEM_API_KEY` or `~/.aem/credentials`).
- Datasets: search, get, schema, preview, request access, access status.
- Models: search and get.
- Notebooks: create, start, stop, run code and wait for the result, list outputs, request exports.
- Exports: list and download approved models, with a checksum check.
- Inside AEM notebooks: `load_data`, `list_datasets`, `list_models`, `model_path`, `save_model`.
- Clear errors for every API failure; automatic retries for passing failures.
- `aem.SandboxUnavailableError` when the server can't run notebook code yet (not retried).
- Talks to `https://marketplace.entelligence.africa/api` by default (`AEM_BASE_URL` overrides it).

## 0.0.1

- Name reserved on PyPI.
