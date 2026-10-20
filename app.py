"""
Batch PDF Signer — local desktop app
Features:
- Batch-select PDFs and preserve originals
- Visual signature image stamping (PNG/JPG)
- Apply to all pages, selected page numbers/ranges, or first/last page
- Position presets and custom x/y placement
- Preview signature size/position settings
- Optional certificate-based digital signing through pyHanko (requires a PEM private key + certificate)
- Per-file status and output folder selection

Visual stamping is not a cryptographic digital signature. Use certificate mode for cryptographic signing.
"""
import os
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None

APP_TITLE = "Batch PDF Signer"

def parse_pages(spec, page_count):
    """1-based page spec: 'all', '1,3,5-7', 'first', 'last'."""
    spec = (spec or "all").strip().lower()
    if spec == "all":
        return set(range(0, page_count))
    if spec == "first":
        return {0} if page_count else set()
    if spec == "last":
        return {page_count - 1} if page_count else set()
    result = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bits = part.split("-", 1)
            if not bits[0].strip().isdigit() or not bits[1].strip().isdigit():
                raise ValueError(f"Invalid page range: {part}")
            start, end = int(bits[0]), int(bits[1])
            if start < 1 or end < start or end > page_count:
                raise ValueError(f"Page range {part} is outside 1–{page_count}")
            result.update(range(start - 1, end))
        else:
            if not part.isdigit():
                raise ValueError(f"Invalid page number: {part}")
            n = int(part)
            if n < 1 or n > page_count:
                raise ValueError(f"Page {n} is outside 1–{page_count}")
            result.add(n - 1)
    return result

def extract_signature_image(source_path, output_path, threshold=245, crop_padding=8):
    """
    Create a transparent PNG from a signature photographed/scanned on a light background.
    Light pixels become transparent; darker ink remains, then the result is tightly cropped.
    Works best when the signature is dark ink on white/off-white paper.
    """
    if Image is None:
        raise RuntimeError("Pillow is not installed. Run: pip install -r requirements.txt")

    im = Image.open(source_path).convert("RGBA")
    pixels = im.load()
    w, h = im.size
    alpha_mask = Image.new("L", (w, h), 0)
    mp = alpha_mask.load()

    # Map whiteness to transparency. White/off-white paper disappears while ink remains.
    # Pixels below threshold retain progressively more opacity.
    for y in range(h):
        for x in range(w):
            r, g, b, _ = pixels[x, y]
            brightness = (r + g + b) / 3.0
            # White paper (near 255) -> alpha 0; dark ink -> alpha 255.
            a = int(max(0, min(255, (threshold - brightness) * 255 / max(threshold - 35, 1))))
            # Suppress tiny compression/noise around paper white.
            if brightness >= threshold:
                a = 0
            mp[x, y] = a

    # Use the extracted alpha while retaining original ink colour.
    im.putalpha(alpha_mask)
    bbox = alpha_mask.getbbox()
    if not bbox:
        raise ValueError("No signature/ink detected. Try a clearer, darker signature image on a light background.")
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - crop_padding)
    y0 = max(0, y0 - crop_padding)
    x1 = min(w, x1 + crop_padding)
    y1 = min(h, y1 + crop_padding)
    im = im.crop((x0, y0, x1, y1))
    im.save(output_path, "PNG")
    return output_path


def stamp_pdf(src, dst, image_path, page_spec, position, width_pct, margin, custom_x, custom_y):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. Run: pip install -r requirements.txt")
    doc = fitz.open(src)
    try:
        pages = parse_pages(page_spec, len(doc))
        if not pages:
            raise ValueError("No pages selected.")
        img = Image.open(image_path)
        iw, ih = img.size
        aspect = ih / max(iw, 1)
        for idx in sorted(pages):
            page = doc[idx]
            rect = page.rect
            width = rect.width * (float(width_pct) / 100.0)
            height = width * aspect
            # Keep image inside page bounds if signature image is unusually tall.
            max_h = rect.height * 0.30
            if height > max_h:
                height = max_h
                width = height / max(aspect, 0.01)
            m = float(margin)
            if position == "Bottom right":
                x1, y1 = rect.width - m - width, rect.height - m - height
            elif position == "Bottom left":
                x1, y1 = m, rect.height - m - height
            elif position == "Top right":
                x1, y1 = rect.width - m - width, m
            elif position == "Top left":
                x1, y1 = m, m
            elif position == "Center":
                x1, y1 = (rect.width-width)/2, (rect.height-height)/2
            else:  # Custom (% from top-left)
                x1 = rect.width * float(custom_x) / 100.0
                y1 = rect.height * float(custom_y) / 100.0
                x1 = min(max(0, x1), max(0, rect.width-width))
                y1 = min(max(0, y1), max(0, rect.height-height))
            box = fitz.Rect(x1, y1, x1 + width, y1 + height)
            page.insert_image(box, filename=image_path, keep_proportion=True, overlay=True)
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        doc.save(dst, garbage=4, deflate=True)
    finally:
        doc.close()

def digital_sign_pdf(src, dst, key_path, cert_path, password):
    """Certificate-based detached signature using pyHanko."""
    try:
        from pyhanko.sign import signers
        from pyhanko.sign.fields import SigFieldSpec, append_signature_field
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    except ImportError:
        raise RuntimeError("Digital-signature dependencies missing. Run: pip install -r requirements-digital.txt")
    signer = signers.SimpleSigner.load(
        key_file=key_path,
        cert_file=cert_path,
        key_passphrase=(password.encode("utf-8") if password else None),
    )
    if signer is None:
        raise RuntimeError("Could not load private key/certificate. Check the files and password.")
    with open(src, "rb") as inf:
        writer = IncrementalPdfFileWriter(inf)
        # A visible signature appearance requires appearance setup; this creates a valid cryptographic signature.
        meta = signers.PdfSignatureMetadata(field_name="Signature1")
        out = signers.sign_pdf(writer, signature_meta=meta, signer=signer)
        with open(dst, "wb") as outf:
            outf.write(out.getbuffer())

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x760")
        self.minsize(860, 650)
        self.files = []
        self.signature_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Signed PDFs"))
        self.mode = tk.StringVar(value="Visual signature image")
        self.page_spec = tk.StringVar(value="all")
        self.position = tk.StringVar(value="Bottom right")
        self.width_pct = tk.StringVar(value="18")
        self.margin = tk.StringVar(value="36")
        self.custom_x = tk.StringVar(value="70")
        self.custom_y = tk.StringVar(value="80")
        self.key_path = tk.StringVar()
        self.cert_path = tk.StringVar()
        self.key_password = tk.StringVar()
        self.status = tk.StringVar(value="Add PDF files to begin.")
        self._build()

    def _build(self):
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="Batch PDF Signer", font=("TkDefaultFont", 20, "bold")).pack(anchor="w")
        ttk.Label(root, text="Batch processing • multi-page placement • local files • optional certificate signing").pack(anchor="w", pady=(0, 12))

        file_frame = ttk.LabelFrame(root, text="1. PDF files", padding=10)
        file_frame.pack(fill="both", expand=True)
        bar = ttk.Frame(file_frame)
        bar.pack(fill="x")
        ttk.Button(bar, text="Add PDFs…", command=self.add_files).pack(side="left")
        ttk.Button(bar, text="Add folder…", command=self.add_folder).pack(side="left", padx=6)
        ttk.Button(bar, text="Remove selected", command=self.remove_selected).pack(side="left")
        ttk.Button(bar, text="Clear", command=self.clear_files).pack(side="left", padx=6)
        self.listbox = tk.Listbox(file_frame, height=7, selectmode=tk.EXTENDED)
        self.listbox.pack(fill="both", expand=True, pady=(8, 0))

        options = ttk.LabelFrame(root, text="2. Signing options", padding=10)
        options.pack(fill="x", pady=10)
        row = ttk.Frame(options); row.pack(fill="x", pady=3)
        ttk.Label(row, text="Signature mode:", width=18).pack(side="left")
        modebox = ttk.Combobox(row, textvariable=self.mode, state="readonly", values=["Visual signature image", "Certificate digital signature"])
        modebox.pack(side="left", fill="x", expand=True)
        modebox.bind("<<ComboboxSelected>>", lambda e: self._toggle_mode())

        self.visual_frame = ttk.Frame(options)
        self.visual_frame.pack(fill="x")
        r = ttk.Frame(self.visual_frame); r.pack(fill="x", pady=3)
        ttk.Label(r, text="Signature image:", width=18).pack(side="left")
        ttk.Entry(r, textvariable=self.signature_path).pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="Choose image…", command=self.choose_signature).pack(side="left", padx=(6,0))
        ttk.Button(r, text="Extract signature…", command=self.extract_signature).pack(side="left", padx=(6,0))
        r = ttk.Frame(self.visual_frame); r.pack(fill="x", pady=3)
        ttk.Label(r, text="Pages:", width=18).pack(side="left")
        ttk.Entry(r, textvariable=self.page_spec, width=22).pack(side="left")
        ttk.Label(r, text="all / first / last / 1,3,5-7").pack(side="left", padx=8)
        r = ttk.Frame(self.visual_frame); r.pack(fill="x", pady=3)
        ttk.Label(r, text="Position:", width=18).pack(side="left")
        ttk.Combobox(r, textvariable=self.position, state="readonly",
                     values=["Bottom right", "Bottom left", "Top right", "Top left", "Center", "Custom"]).pack(side="left")
        ttk.Label(r, text="Width (% page):").pack(side="left", padx=(14,4))
        ttk.Entry(r, textvariable=self.width_pct, width=6).pack(side="left")
        ttk.Label(r, text="Margin (pt):").pack(side="left", padx=(14,4))
        ttk.Entry(r, textvariable=self.margin, width=6).pack(side="left")
        r = ttk.Frame(self.visual_frame); r.pack(fill="x", pady=3)
        ttk.Label(r, text="Custom x/y (%):", width=18).pack(side="left")
        ttk.Label(r, text="X from left").pack(side="left")
        ttk.Entry(r, textvariable=self.custom_x, width=6).pack(side="left", padx=4)
        ttk.Label(r, text="Y from top").pack(side="left")
        ttk.Entry(r, textvariable=self.custom_y, width=6).pack(side="left", padx=4)
        ttk.Label(r, text="(used only for Custom position)").pack(side="left", padx=6)

        self.digital_frame = ttk.Frame(options)
        r = ttk.Frame(self.digital_frame); r.pack(fill="x", pady=3)
        ttk.Label(r, text="Private key (.pem):", width=18).pack(side="left")
        ttk.Entry(r, textvariable=self.key_path).pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="Choose…", command=lambda: self.choose_file(self.key_path, [("PEM files","*.pem"),("All files","*.*")])).pack(side="left", padx=6)
        r = ttk.Frame(self.digital_frame); r.pack(fill="x", pady=3)
        ttk.Label(r, text="Certificate (.pem):", width=18).pack(side="left")
        ttk.Entry(r, textvariable=self.cert_path).pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="Choose…", command=lambda: self.choose_file(self.cert_path, [("PEM files","*.pem *.crt"),("All files","*.*")])).pack(side="left", padx=6)
        r = ttk.Frame(self.digital_frame); r.pack(fill="x", pady=3)
        ttk.Label(r, text="Key password:", width=18).pack(side="left")
        ttk.Entry(r, textvariable=self.key_password, show="•").pack(side="left", fill="x", expand=True)
        ttk.Label(self.digital_frame, text="Uses a PEM private key + certificate. This is not a USB-token/DSC integration.").pack(anchor="w", pady=3)

        out = ttk.LabelFrame(root, text="3. Output", padding=10)
        out.pack(fill="x")
        r = ttk.Frame(out); r.pack(fill="x")
        ttk.Label(r, text="Output folder:", width=18).pack(side="left")
        ttk.Entry(r, textvariable=self.output_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="Choose…", command=self.choose_output).pack(side="left", padx=6)
        r = ttk.Frame(root); r.pack(fill="x", pady=(10,0))
        self.run_button = ttk.Button(r, text="Sign selected PDFs", command=self.start)
        self.run_button.pack(side="left")
        ttk.Button(r, text="Open output folder", command=self.open_output).pack(side="left", padx=8)
        ttk.Label(r, textvariable=self.status).pack(side="left", padx=10)
        ttk.Label(root, text="Important: visual stamping places an image on the page; it does not prove signer identity or prevent tampering. Always keep originals.", foreground="#8a3d00", wraplength=900).pack(anchor="w", pady=(10,0))

    def _toggle_mode(self):
        if self.mode.get() == "Visual signature image":
            self.digital_frame.pack_forget()
            self.visual_frame.pack(fill="x")
        else:
            self.visual_frame.pack_forget()
            self.digital_frame.pack(fill="x")

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Select PDF files", filetypes=[("PDF files","*.pdf")])
        self._add(paths)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Choose folder containing PDFs")
        if folder:
            self._add(sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".pdf")))

    def _add(self, paths):
        existing = set(self.files)
        for p in paths:
            if p not in existing and os.path.isfile(p):
                self.files.append(p)
                self.listbox.insert("end", p)
                existing.add(p)
        self.status.set(f"{len(self.files)} PDF(s) queued.")

    def remove_selected(self):
        inds = list(self.listbox.curselection())
        for i in reversed(inds):
            self.listbox.delete(i)
            del self.files[i]
        self.status.set(f"{len(self.files)} PDF(s) queued.")

    def clear_files(self):
        self.files.clear()
        self.listbox.delete(0, "end")
        self.status.set("Queue cleared.")

    def choose_signature(self):
        p = filedialog.askopenfilename(title="Choose signature image", filetypes=[("Image files","*.png *.jpg *.jpeg"),("All files","*.*")])
        if p: self.signature_path.set(p)

    def extract_signature(self):
        source = filedialog.askopenfilename(
            title="Choose a photo or scan containing the signature",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp *.tif *.tiff"), ("All files", "*.*")]
        )
        if not source:
            return
        default_name = os.path.splitext(os.path.basename(source))[0] + "_signature.png"
        destination = filedialog.asksaveasfilename(
            title="Save extracted transparent signature",
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")]
        )
        if not destination:
            return
        try:
            extract_signature_image(source, destination)
            self.signature_path.set(destination)
            messagebox.showinfo(
                "Signature extracted",
                "Created a transparent PNG with the signature cropped from the image. "
                "Inspect it before signing; if the source has shadows or a dark background, use a clearer scan."
            )
        except Exception as e:
            messagebox.showerror("Could not extract signature", str(e))

    def choose_file(self, var, types):
        p = filedialog.askopenfilename(filetypes=types)
        if p: var.set(p)

    def choose_output(self):
        p = filedialog.askdirectory(title="Choose output folder")
        if p: self.output_dir.set(p)

    def open_output(self):
        p = self.output_dir.get()
        os.makedirs(p, exist_ok=True)
        try:
            if os.name == "nt": os.startfile(p)
            elif sys_platform() == "darwin": os.system('open "{}"'.format(p.replace('"','\\"')))
            else: os.system('xdg-open "{}"'.format(p.replace('"','\\"')))
        except Exception as e:
            messagebox.showerror("Could not open folder", str(e))

    def start(self):
        if not self.files:
            messagebox.showwarning("No PDFs", "Add at least one PDF file.")
            return
        if self.mode.get() == "Visual signature image":
            if not self.signature_path.get() or not os.path.isfile(self.signature_path.get()):
                messagebox.showwarning("Signature image required", "Choose a PNG or JPG signature image.")
                return
            try:
                w = float(self.width_pct.get()); m = float(self.margin.get())
                if not 1 <= w <= 80 or m < 0: raise ValueError()
                if self.position.get() == "Custom":
                    if not (0 <= float(self.custom_x.get()) <= 100 and 0 <= float(self.custom_y.get()) <= 100): raise ValueError()
            except ValueError:
                messagebox.showwarning("Invalid placement", "Width must be 1–80%, margin non-negative, and custom X/Y between 0 and 100.")
                return
        else:
            if not os.path.isfile(self.key_path.get()) or not os.path.isfile(self.cert_path.get()):
                messagebox.showwarning("Certificate files required", "Choose a private key PEM and certificate PEM.")
                return
        self.run_button.configure(state="disabled")
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        outdir = self.output_dir.get()
        os.makedirs(outdir, exist_ok=True)
        success, failures = 0, []
        total = len(self.files)
        for i, src in enumerate(self.files, 1):
            try:
                stem = os.path.splitext(os.path.basename(src))[0]
                dst = os.path.join(outdir, stem + "_signed.pdf")
                if os.path.abspath(src) == os.path.abspath(dst):
                    raise RuntimeError("Output would overwrite the original file.")
                if self.mode.get() == "Visual signature image":
                    stamp_pdf(src, dst, self.signature_path.get(), self.page_spec.get(),
                              self.position.get(), self.width_pct.get(), self.margin.get(),
                              self.custom_x.get(), self.custom_y.get())
                else:
                    digital_sign_pdf(src, dst, self.key_path.get(), self.cert_path.get(), self.key_password.get())
                success += 1
                self.after(0, lambda i=i, total=total, name=os.path.basename(src): self.status.set(f"{i}/{total}: signed {name}"))
            except Exception as e:
                failures.append(f"{os.path.basename(src)}: {e}")
        self.after(0, lambda: self._finish(success, failures, total))

    def _finish(self, success, failures, total):
        self.run_button.configure(state="normal")
        self.status.set(f"Finished: {success}/{total} successful.")
        msg = f"Completed {success} of {total} PDF(s).\nOutput: {self.output_dir.get()}"
        if failures:
            msg += "\n\nFailed files:\n" + "\n".join(failures[:15])
            if len(failures) > 15: msg += f"\n… and {len(failures)-15} more."
            messagebox.showwarning("Batch completed with errors", msg)
        else:
            messagebox.showinfo("Batch complete", msg)

def sys_platform():
    import sys
    return sys.platform

if __name__ == "__main__":
    App().mainloop()
