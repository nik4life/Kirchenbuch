from __future__ import annotations
import argparse, json, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote
import img2pdf, requests
from PIL import Image
from playwright.sync_api import sync_playwright

BANDS={
"918":{"title":"Stollhofen katholisch - Geburten 1804-1835","url":"https://www.landesarchiv-bw.de/plink/?f=4-1120124","slug":"918_Geburten_1804-1835"},
"919":{"title":"Stollhofen katholisch - Geburten 1836-1869","url":"https://www.landesarchiv-bw.de/plink/?f=4-1120125","slug":"919_Geburten_1836-1869"},
"920":{"title":"Stollhofen katholisch - Heiraten 1809-1870","url":"https://www.landesarchiv-bw.de/plink/?f=4-1120126","slug":"920_Heiraten_1809-1870"},
"921":{"title":"Stollhofen katholisch - Sterbefaelle 1809-1870","url":"https://www.landesarchiv-bw.de/plink/?f=4-1120127","slug":"921_Sterbefaelle_1809-1870","bestand":"12390","id":"2556102"}}
DOWNLOAD_RE=re.compile(r"/ofs21/bild_zoom/download\.php",re.I)

def args():
 p=argparse.ArgumentParser()
 p.add_argument("band",choices=[*BANDS,"all"]);p.add_argument("--output",default="output")
 p.add_argument("--delay",type=float,default=1.5);p.add_argument("--headed",action="store_true")
 p.add_argument("--images-only",action="store_true");return p.parse_args()

def dlurl(u):
 if not u or not DOWNLOAD_RE.search(u): return None
 q=parse_qs(urlparse(u).query)
 return u if q.get("id") and q.get("bilddatei") else None

def enter(page,url):
 page.goto(url,wait_until="domcontentloaded");page.wait_for_timeout(1200); print("PERMALINK_FINAL", page.url)
 for i in range(page.locator("a").count()):
  a=page.locator("a").nth(i)
  try:
   t=(a.inner_text() or "").lower();h=a.get_attribute("href") or ""
   if "archivalien-viewer" in t or "bild_zoom" in h or "ofs21" in h:
    page.goto(urljoin(page.url,h),wait_until="domcontentloaded");page.wait_for_timeout(1200); print("VIEWER_URL", page.url); return
  except Exception: pass
 if "ofs21" not in page.url: raise RuntimeError("Archivalien-Viewer-Link nicht gefunden")

def collect(page):
 found=[];seen=set()
 def add(u):
  u=dlurl(u)
  if u and u not in seen: seen.add(u);found.append(u)
 page.on("request",lambda r:add(r.url));page.on("response",lambda r:add(r.url))
 for _ in range(5000):
  for h in page.locator("a").evaluate_all("(e)=>e.map(x=>x.href)"): add(h)
  html=page.content()
  for m in re.findall(r'https?://[^"\'<> ]+download\.php\?[^"\'<> ]+',html,re.I): add(m.replace("&amp;","&"))
  nxt=page.locator('a[title*="näch" i],a[title*="weiter" i],a[aria-label*="näch" i]')
  if not nxt.count():
   nxt=page.get_by_role("link",name=re.compile(r"^(weiter|nächste|naechste|next|>)",re.I))
  try:
   if not nxt.count() or not nxt.first.is_visible(): break
   before=page.url;nxt.first.click();page.wait_for_timeout(800)
   try: page.wait_for_load_state("domcontentloaded",timeout=4000)
   except Exception: pass
   if page.url==before and len(found)==0: break
  except Exception: break
 return found

def direct_urls(c):
 bestand=c.get("bestand"); image_id=c.get("id")
 if not bestand or not image_id: return []
 base="https://www2.landesarchiv-bw.de/ofs21/bild_zoom/"
 first=f"{base}thumbnails.php?bestand={bestand}&id={image_id}&syssuche=&logik=und"
 session=requests.Session()
 session.headers["User-Agent"]="Mozilla/5.0 Kirchenbuch private genealogy research"
 queue=[first]; seen_pages=set(); names=[]; seen_names=set()
 while queue:
  url=queue.pop(0)
  if url in seen_pages: continue
  seen_pages.add(url)
  r=session.get(url,timeout=60); r.raise_for_status(); html=r.text
  print("THUMBNAILS_PAGE",len(seen_pages),r.status_code,r.url,"bytes",len(r.content))
  for raw in re.findall(r"(?:gewaehlteSeite|bilddatei)=([^&\"'<> ]+)",html,re.I):
   name=unquote(raw.replace("&amp;","&"))
   if name not in seen_names:
    seen_names.add(name); names.append(name)
  if not names:
   for name in re.findall(r"([A-Za-z0-9_.-]+\\.(?:jpe?g|png|tiff?|webp))",html,re.I):
    if name not in seen_names:
     seen_names.add(name); names.append(name)
  # OFS21 exposes the thumbnail pagination as links back to thumbnails.php.
  for href in re.findall(r'href=[\"\\\']([^\"\\\']*thumbnails\\.php[^\"\\\']*)[\"\\\']',html,re.I):
   href=href.replace("&amp;","&")
   nxt=urljoin(r.url,href)
   q=parse_qs(urlparse(nxt).query)
   if q.get("bestand",[bestand])[0] != bestand: continue
   if q.get("id",[image_id])[0] != image_id: continue
   if nxt not in seen_pages and nxt not in queue: queue.append(nxt)
  if len(seen_pages)>1000: raise RuntimeError("Thumbnail-Pagination laeuft unerwartet weiter.")
 print("THUMBNAIL_PAGES",len(seen_pages),"DIRECT_FILES",len(names),names[:3],names[-3:] if names else [])
 if not names: return []
 return [f"{base}download.php?id={image_id}&bilddatei={name}" for name in names]

def ext(r,u):
 c=(r.headers.get("content-type") or "").lower()
 if "png" in c:return ".png"
 if "tif" in c:return ".tif"
 if "jpeg" in c or "jpg" in c:return ".jpg"
 return ".jpg"

def download(urls,folder,delay):
 folder.mkdir(parents=True,exist_ok=True)
 (folder/"manifest.json").write_text(json.dumps({"urls":urls},indent=2),encoding="utf-8")
 s=requests.Session();s.headers["User-Agent"]="Kirchenbuch/1.0 private genealogy research";out=[]
 for i,u in enumerate(urls,1):
  old=[p for p in folder.glob(f"{i:04d}.*") if p.suffix.lower() in {".jpg",".jpeg",".png",".tif",".tiff"}]
  if old: out.append(old[0]);continue
  for attempt in range(3):
   try:
    r=s.get(u,timeout=90);r.raise_for_status();p=folder/f"{i:04d}{ext(r,u)}";p.write_bytes(r.content)
    with Image.open(p) as im: im.verify()
    out.append(p);print(f"[{i}/{len(urls)}] {p.name}");break
   except Exception as e:
    if attempt==2: raise RuntimeError(f"Download fehlgeschlagen: {u}") from e
    time.sleep(2*(attempt+1))
  time.sleep(max(0,delay))
 return out

def one(browser,bid,root,delay,images_only):
 c=BANDS[bid];folder=root/c["slug"];page=browser.new_page()
 print("\n"+c["title"])
 urls=direct_urls(c)
 if not urls:
  enter(page,c["url"])
  urls=collect(page)
 page.close()
 if not urls: raise RuntimeError("Keine Download-Links gefunden. Siehe Workflow-Log fuer PERMALINK_FINAL/VIEWER_URL.")
 print(f"{len(urls)} Digitalisate erkannt")
 imgs=download(urls,folder,delay)
 if not images_only:
  pdf=root/(c["slug"]+".pdf")
  pdf.write_bytes(img2pdf.convert([str(x) for x in imgs]))
  print("PDF:",pdf)

def main():
 a=args();root=Path(a.output);root.mkdir(parents=True,exist_ok=True);targets=list(BANDS) if a.band=="all" else [a.band]
 with sync_playwright() as p:
  b=p.chromium.launch(headless=not a.headed)
  try:
   for x in targets: one(b,x,root,a.delay,a.images_only)
  finally:b.close()
if __name__=="__main__":main()
