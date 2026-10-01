# Kirchenbuch

Downloader für die öffentlich im Online-Findmittelsystem des Landesarchivs Baden-Württemberg bereitgestellten katholischen Kirchenbücher von Stollhofen.

Er öffnet den regulären Archivalien-Viewer, sammelt dessen Download-Links, lädt alle Seiten nacheinander und erzeugt daraus eine PDF. Zugangsbeschränkungen werden nicht umgangen.

## Bände

- 918: Geburten 1804–1835
- 919: Geburten 1836–1869
- 920: Heiraten 1809–1870
- 921: Sterbefälle 1809–1870

## Windows-Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

## Test

```powershell
python kirchenbuch.py 918 --headed
```

Danach:

```powershell
python kirchenbuch.py 918
python kirchenbuch.py all
```

Ausgabe: `output/`. Bereits vorhandene nummerierte Bilder werden übersprungen (Resume). Pro Band wird außerdem `manifest.json` gespeichert.

Falls der LABW-Viewer seine Navigation ändert, zuerst mit `--headed` starten. Das Programm verwendet ausschließlich Download-Links, die der normale Viewer selbst bereitstellt.
