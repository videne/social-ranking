# social-ranking

Clasamentul postărilor de Instagram și TikTok după eficiență (views, like-uri, comentarii, salvări, distribuiri), cu filtru pe 7 / 30 / 90 de zile sau de la 1 ianuarie.

**Site:** https://videne.github.io/social-ranking/

## Cum adaugi date noi
1. Descarcă exportul CSV:
   - **Instagram:** Meta Business Suite → Statistici → Conținut → Exportă date → Instagram → Postări.
   - **TikTok:** TikTok Studio (pe calculator) → Analize → Conținut → descarcă datele pe postări.
2. Aici pe GitHub intră în folderul `instagram/` sau `tiktok/` → **Add file → Upload files** → trage fișierul → **Commit changes**.
3. Site-ul se actualizează singur în 1–2 minute (tabul **Actions** arată progresul).

Exporturile se pot suprapune: aceeași postare apare o singură dată, cu cifrele cele mai noi.
Fișierele cu totaluri pe zi (de ex. `Overview.csv` de la TikTok) apar ca rezumat pe perioadă, nu în clasament.

## Formula
```
implicare = like + 3·comentarii + 4·salvări + 5·distribuiri
rată      = (implicare + k·rata medie a contului) ÷ (vizualizări + k),  k = 0,25 · mediana vizualizărilor
eficiență = (rată ÷ mediana ratei)^0,7 × (vizualizări ÷ mediana vizualizărilor)^0,3
scor      = 100 ÷ (1 + eficiență^−1,6)          → 50 = o postare tipică pentru cont
```
Medianele se calculează pe fiecare cont și platformă separat, pe toate postările din fișiere.
Conturile cu sub 10 postări (colaborări) sunt comparate împreună.

## Fișiere
- `index.html` — aplicația
- `build.py` — citește CSV-urile și produce `site/data.json`
- `.github/workflows/pages.yml` — rulează `build.py` și publică site-ul la fiecare modificare
