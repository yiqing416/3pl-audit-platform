"use client";

import { useState } from "react";

type UploadResponse = {
  filename: string;
  headers: string[];
  parsed_rows: number;
  preview: Array<{
    fee_type_raw: string;
    amount: string;
    order_ref?: string | null;
    tracking_ref?: string | null;
  }>;
};


export default function UploadPage() {
  const API_BASE =
    process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string>("");
  const [result, setResult] = useState<UploadResponse | null>(null);

  async function handleUpload() {
    if (!file) {
      setStatus("Please choose a CSV file first.");
      return;
    }

    setStatus("Uploading...");
    setResult(null);

    const form = new FormData();
    form.append("file", file); // the key name must match FastAPI parameter: file

    try {
      const res = await fetch(`${API_BASE}/upload`, {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        const text = await res.text();
        setStatus(`Upload failed: ${text}`);
        return;
      }

      const data = (await res.json()) as UploadResponse;
      setResult(data);
      setStatus("Upload succeeded ✅");
    } catch (e: any) {
      setStatus(`Network error: ${e?.message || "unknown"}`);
    }
  }

  return (
    <main className="p-8 space-y-4">
      <h1 className="text-2xl font-bold">Upload Invoice CSV</h1>

      <p className="text-sm text-gray-600">
        Frontend (Next.js) is sending your file to:{" "}
        <code className="bg-gray-100 px-2 py-1 rounded">
          {API_BASE}/upload
        </code>
      </p>

      <input
        type="file"
        accept=".csv"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />

      <button
        onClick={handleUpload}
        className="px-4 py-2 rounded bg-black text-white disabled:opacity-50"
        disabled={!file}
      >
        Upload
      </button>

      {status && <div className="font-medium">{status}</div>}

      {result && (
        <div className="space-y-3">
            <div><b>Filename:</b> {result.filename}</div>
            <div><b>Parsed rows:</b> {result.parsed_rows}</div>
            <div><b>Headers:</b> {result.headers.join(", ")}</div>

            <table className="border-collapse border w-full">
            <thead>
                <tr>
                <th className="border p-2">fee_type_raw</th>
                <th className="border p-2">amount</th>
                <th className="border p-2">order_ref</th>
                <th className="border p-2">tracking_ref</th>
                </tr>
            </thead>
            <tbody>
                {result.preview.map((r, i) => (
                <tr key={i}>
                    <td className="border p-2">{r.fee_type_raw}</td>
                    <td className="border p-2">{r.amount}</td>
                    <td className="border p-2">{r.order_ref ?? ""}</td>
                    <td className="border p-2">{r.tracking_ref ?? ""}</td>
                </tr>
                ))}
            </tbody>
            </table>
        </div>
        )}
    </main>
  );
}
