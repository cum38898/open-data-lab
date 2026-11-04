import { loadDataset, toSearchRow } from "../../lib/data";

export function GET() {
  const rows = loadDataset().records.map(toSearchRow);
  return new Response(JSON.stringify(rows), { headers: { "Content-Type": "application/json" } });
}
