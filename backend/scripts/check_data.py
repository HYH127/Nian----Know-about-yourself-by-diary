import httpx

r = httpx.get("http://localhost:8000/api/diary")
diaries = r.json()
print(f"Total diaries: {len(diaries)}")
for d in diaries[:5]:
    print(f"  {d['id'][:8]} | {d['date']} | {d['content'][:40]}")

r2 = httpx.get("http://localhost:8000/api/profile")
fragments = r2.json()
print(f"\nTotal profile fragments: {len(fragments)}")
sources = [f for f in fragments if f.get('source')]
print(f"Fragments with source: {len(sources)}")
for f in sources[:3]:
    print(f"  id={f['id'][:8]} source={f['source']} dim={f['dimension']}")