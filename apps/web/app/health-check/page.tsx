export default async function HealthCheckPage() {
  const base = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

  let data: any = null;
  let error: string | null = null;

  try {
    const res = await fetch(`${base}/health`, { cache: "no-store" });
    if (!res.ok) {
      error = `Backend responded with ${res.status}`;
    } else {
      data = await res.json();
    }
  } catch (e: any) {
    error = e?.message || "Failed to fetch backend";
  }

  return (
    <main style={{ padding: 24, fontFamily: "system-ui" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>Health Check</h1>

      <p>
        Frontend is calling: <code>{base}/health</code>
      </p>

      {error ? (
        <div style={{ marginTop: 12, color: "crimson" }}>
          <b>Error:</b> {error}
        </div>
      ) : (
        <pre
          style={{
            marginTop: 12,
            background: "#f3f4f6",
            padding: 12,
            borderRadius: 8,
          }}
        >
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </main>
  );
}
