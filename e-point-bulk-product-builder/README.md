# e·Point CSV Studio

Prijenosni Windows program za pripremu jednostavnih WooCommerce proizvoda iz Excel tablica, istraživanje proizvođačkih podataka, pregled i CSV izvoz. Sučelje je na hrvatskom. Izvedba 1.0.0.

## Pokretanje

Pokrenite `ePoint CSV Studio.exe`. Na korisničkom računalu nisu potrebni Python, Excel ni dodatni paketi. Cilj je 64-bitni Windows 10/11. Podaci se spremaju u mapu `data` uz program. Ako ona nije zapisiva, program koristi `%LOCALAPPDATA%/ePointCSV` i prikazuje stvarnu putanju u logu.

## Prva obrada

1. **Učitaj Excel / CSV**: odaberite `.xlsx`, `.xlsm`, `.xls`, `.csv` ili `.tsv`, list i redak zaglavlja. Provjerite mapiranje stupaca. Upišite naziv profila dobavljača za ponovno korištenje mapiranja. Više učitavanja dodaje proizvode u isti katalog.
2. **Postavke**: provjerite PDV, cijene, model, API limit, proizvođačke domene i kategorije.
3. **Obradi nepotvrđene**: odaberite **Tokenless preglednik** za Playwright/Chromium pretraživanje bez OpenAI tokena, AI istraživanje, Izravni URL bez AI-ja ili Provjeri slike. Gumb **Ponovi** ponovno obrađuje samo odabrani proizvod i zanemaruje predmemoriju.
4. **Pregled**: otvorite proizvođački izvor i slike. Provjerite točan model, kapacitet, boju, regiju/paket, opise i kategoriju. Uredite polja pa kliknite **Potvrdi i dalje**. Promjena proizvoda ili njegove cijene poništava prethodnu potvrdu.
5. **Izradi WooCommerce CSV**: odaberite način i izlaznu mapu. Svaki izvoz dobiva novu mapu i provjerava se ponovnim čitanjem spremljenog CSV-a.

## Pravila cijena

- Početna pretpostavka: **VPC i Akcija VPC su bez PDV-a**. Izlaz uključuje 25% PDV-a. Primjer: 100 EUR → 125,00 EUR. U postavkama se mogu promijeniti PDV i način ulaznih cijena.
- Zadano: ako postoji Akcija VPC koristi se ona; inače obični VPC. Odabrana cijena s PDV-om ide u `Regular price`. Dodatna marža se ne dodaje.
- Opcija redovne i akcijske: `Regular price = VPC × 1,25`; `Sale price = Akcija VPC × 1,25`. Ako postoji samo akcijska VPC, koristi se kao jedina prodajna cijena, bez izmišljene redovne cijene.
- Prazna akcijska ćelija dopušta obični VPC. Neispravna/nejasna akcijska vrijednost znači preskakanje retka.
- Računanje koristi decimalnu aritmetiku i zaokruživanje na dvije decimale, pola centa prema gore. Negativne/nulte cijene i akcijska cijena koja nije manja od redovne se odbijaju.
- Podržano: `1299.99`, `1299,99`, `1.299,99 €`, `1,299.99 EUR`. Nejasno `1.250` zahtijeva ispravak u `1250` ili `1250,00`. Ulazne cijene s više od dvije decimale zahtijevaju prethodno dogovoreno zaokruživanje.
- **WooCommerce mora biti postavljen na unos cijena s uključenim porezom.** Program ne mijenja postavke trgovine. Valuta programa je EUR.

## Internet i OpenAI API

### Tokenless preglednik

Način **Tokenless preglednik** koristi stvarni lokalni Chromium kroz Playwright. Ne koristi OpenAI API, API ključ ni model. Ako je proizvođački URL upisan u Excelu, preglednik otvara taj URL. Ako nije upisan, koristi javnu web pretragu i prihvaća samo rezultat na dopuštenoj proizvođačkoj domeni. Program potom čita dinamički HTML, naslov, javne slike i tekst te provjerava model/EAN gdje je moguće.

CAPTCHA, robots.txt, prijava, HTTP 403/429, nejasna domena i nečitljiv sadržaj uzrokuju preskakanje proizvoda. Program ne pokušava zaobići zaštitu. Slike koje nisu javni HTTP(S) URL-ovi preskaču se, a obrada se nastavlja s provjerenim slikama.

Distribucija uključuje mapu `ms-playwright` uz EXE. Ako ručno izrađujete program iz izvornog koda, prvo pokrenite `python -m playwright install chromium`.

API ključ unesite u aplikaciju, u **Postavke → Istraživanje i API**. Po želji se sprema šifrirano Windows DPAPI-jem, vezano uz Windows korisnički račun. Projekt i log ne sadrže ključ. Na drugom računalu ključ unesite ponovno.

AI istraživanje koristi OpenAI Responses API s web pretragom i provjerljivom strukturom odgovora. Početni model je `gpt-6-astra`; možete odabrati drugi ponuđeni model dostupan na svom API računu. API i web pretraga naplaćuju se prema API računu. Početni limit je 20 proizvoda po pokretanju, promjenjiv do 5000. Jedan proizvod dopušta najviše 4 ugrađena poziva alata i 6000 izlaznih tokena. To su tehnički limiti, a ne fiksna cijena u eurima; novčani limit postavite na API računu.

API dobiva naziv, brend, proizvođački model, EAN, izvorni URL i dopuštene kategorije. VPC i cijela ulazna tablica se ne šalju. Upute traže originalne hrvatske opise isključivo iz službenog proizvođačkog izvora. Program provjerava da je URL doista korišten u web pretrazi, preuzima stranicu, provjerava identifikacijske oznake, citate specifikacija i postojanje URL-ova slika u izvornom sadržaju. Rezultat ostaje **Za pregled**: provjera tekstualnih oznaka ne jamči da su sve tvrdnje, varijante ili slike automatski ispravne. Korisnička potvrda je dio postupka.

Unesite proizvođačke domene za ograničavanje izvora. Prazan popis dopušta modelu pronalaženje proizvođača; pripadnost domene proizvođaču tada potvrđujete pri pregledu. Neispravan identitet, izvor, citat ili slike preskaču proizvod uz razlog. CAPTCHA, 403, 429 i zabrana u robots.txt prekidaju pristup tom izvoru; nema zaobilaženja. Izvori koji zahtijevaju JavaScript, prijavu ili PDF obradu mogu ostati nedostupni.

**Izravni URL bez AI-ja** koristi javni strukturirani `Product` JSON-LD na proizvođačkom URL-u zadanom u Excelu ili sučelju. Ne troši API sredstva. Opis ostaje na izvornom jeziku pa po potrebi uredite hrvatski tekst. Ovaj način ne traži internetom proizvođača ako URL nije zadan.

Slike moraju biti izravni javni JPEG/PNG/WebP/GIF/AVIF URL-ovi, do 20 MB po datoteci. Program provjerava HTTP odgovor, tip i početne bajtove slike. To provjerava dohvatljivost/format; pripadnost modelu i pravo korištenja potvrđuje korisnik. Provjera slika vrijedi 24 sata prije izvoza. Cjelovitost dekodiranja slika i uspjeh njihova preuzimanja s WooCommerce poslužitelja nisu automatski dokazani.

## Postojeći proizvodi

Za **Samo novi**, **Samo ažuriranje** i **Odvojeno novi i ažuriranje** učitajte aktualni CSV izvoz WooCommerce kataloga. Prepoznavanje koristi SKU ili EAN iz kataloga, a ažuriranje izvozi postojeći SKU/ID. Dvosmisleni rezultati, sukobi identifikatora i proizvodi koji nisu `simple` se preskaču. Naziv sam po sebi nije dovoljan za pouzdano povezivanje s postojećim proizvodom.

Ako ulaz nema SKU, program koristi `EAN-<EAN>` ili stabilnu `EP-<oznaku iz naziva>`. Takav SKU nije automatski postojeći SKU trgovine. Promjena naziva može promijeniti automatski generirani SKU; zato se preporučuje stvarna stabilna šifra.

**Svi za novi unos** priprema nove proizvode. Ako je katalog učitan, postojeći se preskaču; bez kataloga njihovo preskakanje prepušteno je ugrađenom WooCommerce uvozniku.

## Datoteke izvoza i uvoz

- `novi-*.csv`: novi proizvodi, `Type=simple`, `Published=-1` (nacrt).
- `azuriranje-*.csv`: ažuriranje sadržaja i cijena postojećih proizvoda; postojeći status objave i zalihe ostaju nepromijenjeni.
- `izvori.csv`: izvještaj o izvorima, redcima i cijenama. **Ne uvozi se u WordPress.**
- `log.txt`: redci koji su preskočeni i razlozi.
- `izvjestaj.json`: broj ulaznih, izvezenih i preskočenih redaka te postavke izvoza.
- `UPUTE.txt`: kratke upute za pojedini izvoz.

U WooCommerceu otvorite **Proizvodi → Uvoz**. Za `novi-*.csv` isključite **Ažuriraj postojeće proizvode**, a za `azuriranje-*.csv` uključite. Provjerite mapiranje stupaca. Aktualni ugrađeni uvoznik podržava `Brands`; dodatci za brendove ili starije verzije mogu zahtijevati drugačije mapiranje. EAN stupac je `GTIN, UPC, EAN, or ISBN`. U ovoj verziji prazna akcijska cijena se izostavlja i **ne uklanja postojeću akciju**. Namjerno brisanje akcija nije uključeno.

CSV koristi UTF-8 BOM, standardno citiranje navodnicima i decimalnu točku. Odabir razdjelnika je zarez ili točka-zarez. Za otvaranje u Excelu koristite **Podaci → Iz teksta/CSV** i SKU/EAN postavite kao tekst da se sačuvaju vodeće nule. Specifikacije se izvoze kao HTML tablica u dugom opisu. Proizvodne CSV datoteke grupiraju se prema dostupnim poljima kako prazne vrijednosti ne bi prebrisale podatke pri ažuriranju.

Najprije napravite mali probni uvoz na testnoj trgovini ili nacrtima. Program ne prijavljuje se u WordPress i ne provodi uvoz umjesto vas.

## Spremanje i prekid

Radni katalog automatski se sprema nakon svakog dovršenog proizvoda. **Zaustavi** prekida daljnju obradu; aktivni API zahtjev može trajati do 180 sekundi. Neuspješan/neizvjestan naplatni API poziv ne ponavlja se automatski kako se ne bi dvostruko naplatio. Ponovi omogućuje izričit novi pokušaj odabranog retka. Proizvođačka blokada se pamti tijekom pojedinog pokretanja obrade.

Istraženi podaci mogu se ponovno koristiti iz lokalne predmemorije do 7 dana, uz novu provjeru slika i korisnički pregled. Cijene se uvijek računaju iz trenutačnog ulaza. **Spremi projekt** izrađuje `.epcsv` kopiju za prijenos. **Nova obrada** čuva prethodni projekt u `data/arhiva`. Za prijenos profila i predmemorije između računala možete kopirati mapu `data`; šifrirani API ključ vezan je uz račun i na drugom računalu ga ponovno unesite.

## Opseg i provjere

Podržani su jednostavni proizvodi, više ulaznih datoteka i rad s tisućama redaka. Varijacije, inventar/zalihe, izravan WordPress API, automatska objava, PDF dohvat i automatsko uklanjanje postojeće akcije nisu dio verzije 1.0.

Automatizirani testovi obuhvaćaju Excel formule s/bez spremljenog izračuna, hrvatske znakove, cijene i PDV, identifikatore i duplikate, ponovno čitanje CSV-a, tisuću proizvoda, odvojeni unos/ažuriranje, čuvanje postojećih polja, nastavak projekta, simulirane API odgovore i mrežne kvarove. Dostupnost plaćenog API-ja i stvaran WooCommerce uvoz zahtijevaju konfiguriran API račun odnosno testnu trgovinu.

## Izrada iz izvornog koda

Na razvojnom Windows računalu s 64-bitnim Pythonom 3.13:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m tests.gui_smoke
.\build.ps1
```

Izlaz: `dist/ePoint CSV Studio.exe`. Kod se oslanja na Python standardnu biblioteku, Tk, openpyxl, xlrd, requests, BeautifulSoup i jsonschema. Distribucija uključuje te komponente kroz PyInstaller; izgradnja je testirana na razvojnom računalu, a zasebna provjera čistih Windows 10 i Windows 11 računala potrebna je za potvrdu obje platforme.

## Službene reference

- WooCommerce CSV: https://woocommerce.com/document/product-csv-importer-exporter/
- Brendovi: https://woocommerce.com/document/managing-product-taxonomies/product-brands/
- Unos cijena s porezom: https://woocommerce.com/document/setting-up-taxes-in-woocommerce/
- OpenAI web pretraga: https://developers.openai.com/api/docs/guides/tools-web-search
- Strukturirani odgovori: https://developers.openai.com/api/docs/guides/structured-outputs
Napomena za GitHub: izvorni kod i provjereni EXE su uključeni u repozitorij. Velika mapa `dist/ms-playwright` nije uključena u Git zbog veličine; za puni tokenless offline paket pokrenite `build.ps1`, koji je preuzima iz lokalne Playwright instalacije i dodaje uz EXE.

