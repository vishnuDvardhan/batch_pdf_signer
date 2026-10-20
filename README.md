# Batch PDF Signer

A local desktop application for batch PDF processing on Windows, macOS, and Linux.

## Included features
- Add multiple PDFs or every PDF in a folder.
- Save signed copies to a separate output folder; originals are not modified.
- Visual signature image stamping with PNG/JPG.
- Extract a signature from a photo/scan: remove a light paper background, crop tightly, and save a transparent PNG.
- Page selection: all, first, last, or explicit pages/ranges such as `1,3,5-7`.
- Placement presets: bottom-right, bottom-left, top-right, top-left, center, or custom coordinates.
- Adjust signature width and margin.
- Per-file progress and error reporting.
- Optional certificate-based cryptographic signing with a PEM private key and certificate.

## Install and run
Python 3.10+ recommended.

### macOS / Linux
```bash
cd batch_pdf_signer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

### Windows
```powershell
cd batch_pdf_signer
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

## Certificate-based digital signing (optional)
Install the additional dependency:
```bash
python -m pip install -r requirements-digital.txt
```
In the app, select **Certificate digital signature**, then provide a PEM private key and matching PEM certificate. The key may be password protected.

**Important limitations**
- This optional mode is for PEM key/certificate files. It does not directly integrate with Indian USB-token DSC devices, smart cards, cloud signing services, or eSign providers.
- For production/legal use, verify that your certificate chain, timestamping, revocation checks, and applicable jurisdiction requirements are configured appropriately.
- The current certificate mode applies a cryptographic signature field named `Signature1`; it does not create a visible handwritten-style appearance. Cryptographic signing is not the same as stamping a signature image.
- A PDF may already contain signatures or restrictions. Test on copies and validate output with a trusted PDF reader.

## Visual signature stamping
Use a PNG with a transparent background for the cleanest result. It stamps the image onto the chosen pages and is **not** a cryptographic signature or proof of identity.

## Notes
- Page numbers are 1-based.
- Custom X/Y are percentages from the page's top-left corner.
- Output files use the suffix `_signed.pdf`.

### Extracting a signature from a photo
Click **Extract signature…**, choose the photo/scan, then save the extracted PNG. It works best with dark ink on white or off-white paper. Inspect the transparent PNG before applying it; shadows, colored paper, and low-contrast images may need a cleaner source image.
