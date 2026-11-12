# aem-sdk

The official Python library for **AEM, the Africa Entelligence Marketplace**: secure African datasets and models, where the data never leaves its owner.

```bash
pip install aem-sdk
```

## Quickstart

Create an API key on the **API Keys** page of the AEM dashboard, then:

```python
import aem

client = aem.Client(api_key="aem_sk_...")   # or set the AEM_API_KEY environment variable

for ds in client.datasets.search("malaria"):
    print(ds.name, ds.row_count, ds.access_tier)

client.datasets.request_access("aem-demo/primary-care-clinic-visits", purpose="Malaria risk model")
```

## Train next to the data

Restricted data never leaves AEM, so your code goes to the data instead:

```python
nb = client.notebooks.create("Malaria risk", datasets=["aem-demo/primary-care-clinic-visits"])
client.notebooks.start(nb.id)

result = client.notebooks.run(nb.id, """
import aem
from sklearn.linear_model import LogisticRegression

df = aem.load_data("aem-demo/primary-care-clinic-visits")
X, y = df[["feature_a", "feature_b"]], df["label"]   # use the dataset's own columns
model = LogisticRegression().fit(X, y)
aem.save_model(model, "malaria-risk")
""")
print(result.text)

client.notebooks.request_export(nb.id, "malaria-risk.onnx")   # each data owner approves it
```

Once it's approved:

```python
for export in client.exports.list():
    if export.approved:
        client.exports.download(export.id, "models/")
```

## Inside an AEM notebook

The same `import aem` works in notebooks, with direct access to the attached data:

```python
import aem

aem.list_datasets()
df = aem.load_data("aem-demo/primary-care-clinic-visits")
aem.save_model(model, "malaria-risk")
```

## Errors

Every error is an `aem.AEMError`, with a message that says what to do next:

```python
try:
    client.datasets.preview("aem-demo/sme-loan-repayments")
except aem.PreviewUnavailableError as e:
    print(e)   # Row previews are only available for open datasets...
```

## Settings

| Setting | How |
| --- | --- |
| API key | `aem.Client(api_key=...)`, `AEM_API_KEY`, or a file at `~/.aem/credentials` |
| Address | `aem.Client(base_url=...)` or `AEM_BASE_URL` |

Requires Python 3.10 or newer. For data frames, install `pip install "aem-sdk[pandas]"`.
