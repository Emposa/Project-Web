# Provjere izdanja 1.0.0

Datum: 7. rujna 2026.

## Potvrđeno na ovom računalu

- Razvojno okruženje: Windows 11 x64, izdanje sustava 10.0.26200, Python 3.13.5.
- 58 automatiziranih testova prošlo je bez grešaka.
- 1.000 sintetičkih proizvoda izvezeno je u 10 CSV datoteka po 100 redaka, uz ponovno čitanje svih CSV datoteka i usklađene brojeve redaka.
- Provjereni su hrvatski znakovi, navodnici i višeredni opisi, UTF-8 BOM, decimalne cijene i zaokruživanje, prioritet akcijske VPC, dodavanje PDV-a i ulaz koji već uključuje PDV.
- Provjereno je preskakanje nevaljanih cijena, duplikata SKU/EAN, nevaljanog EAN-a, nepotvrđenih i naknadno promijenjenih proizvoda te proizvoda bez provjerenih slika.
- Stvarni XLSX čitač provjeren je na formulama sa spremljenim rezultatom i formulama bez rezultata te tekstualnom SKU-u s vodećim nulama.
- Provjereni su stvarni Tk prozori: učitavanje i mapiranje Excela, arhiviranje, uređivanje opisa i cijena, potvrda, izvoz, promjena postavki, spremanje/otvaranje projekta i nastavak nakon ponovnog pokretanja.
- Sučelje je vizualno pregledano pri 1380×880 i 1100×720; manji prozor nudi pomicanje podataka proizvoda.
- Ugrađeni Windows DPAPI uspješno je šifrirao i dešifrirao sintetički testni ključ.
- Izrađeni samostalni EXE pokrenut je izravno. U zapakiranoj aplikaciji prošli su provjera prozora, Tk/SQLite, decimalni izračun, učitavanje stvarnog XLSX testnog ulaza, učitavanje xlrd/jsonschema i CSV izvoz. Proces je završio izlaznim kodom 0.
- EXE veličina: 23.863.426 bajtova. SHA-256: `E484A791DB5152AB46C30240C8FC8A9F43A602AF56DD78F520FDAC5F63329B82`.

## Stvarna mrežna provjera

Izravan dohvat javne proizvođačke stranice Arduino UNO Rev3 potvrdio je EAN `7630049200050`, preuzeo strukturirani opis i provjerio četiri slikovna URL-a. Proizvod je ispravno ostao u stanju **Za pregled**. Cijena s interneta nije korištena.

Izvor: https://store.arduino.cc/products/arduino-uno-rev3

Provjera dvaju BaByliss proizvodnih URL-ova vratila je HTTP 404. Program je odbio izvore bez zamjene drugim modelom. To potvrđuje obradu nedostupnog izvora, a ne univerzalnu dostupnost proizvođačkih stranica.

## Još nije potvrđeno

- Stvarni naplatni OpenAI API poziv: API ključ nije konfiguriran. Struktura zahtjeva i obrada odgovora, pogrešaka, nepotpunih odgovora i prekida provjerene su simuliranim odgovorima.
- Stvarni WooCommerce uvoz: nije dostupna korisnička testna trgovina ili prihvaćeni izvozni uzorak. Kompatibilnost se temelji na službenoj CSV specifikaciji i lokalnoj provjeri datoteka.
- Zasebno čisto računalo s Windowsom 10 i drugo računalo s Windowsom 11: nisu bili dostupni. Izrada cilja 64-bitni Windows 10/11.
- Korisnikove stvarne dobavljačke tablice: nisu dostavljene. Podržane varijacije mapiranja provjerene su testnim podacima.
- Dostupnost svih proizvođača, potpuna automatska identifikacija varijanti i ispravnost svake AI rečenice nisu zajamčene; zato je pregled proizvoda obvezan prije izvoza.

Program je spreman za početnu lokalnu probu i mali probni WooCommerce uvoz nakon konfiguracije. Ove provjere nisu tvrdnja da je proveden produkcijski uvoz.

