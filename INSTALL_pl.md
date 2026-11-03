# Kerfly: instalacja i pierwsze uruchomienie

Kerfly działa z kodu źródłowego, czyli przez Pythona. Gotowe instalatory
(`.exe`, AppImage) powstaną później.

## Windows 10 / 11

### 1. Python

1. Pobierz **Python 3.13** (zalecany, bo wszystkie biblioteki mają dla niego gotowe paczki):
   <https://www.python.org/downloads/windows/>. Wybierz „Windows installer (64-bit)”
   z najnowszego wydania 3.13.
2. W pierwszym oknie instalatora **zaznacz „Add python.exe to PATH”**, potem
   kliknij „Install Now”.

### 2. Inkscape (opcjonalnie)

Kerfly otwiera pliki SVG sam. Inkscape (<https://inkscape.org/release/>) jest
potrzebny tylko wtedy, gdy SVG zawiera **tekst do cięcia lub grawerowania
konturu** (Kerfly zamienia go wtedy na ścieżki przez Inkscape). Jeśli Inkscape
jest zainstalowany, Kerfly użyje go też do rastra, tak jak K40 Whisperer.

### 3. Sterownik USB lasera (jednorazowo)

Płyta K40 (M2 Nano, układ CH341) potrzebuje sterownika **libusb-win32**:

- Jeśli na tym komputerze działał już **K40 Whisperer**, sterownik jest
  zainstalowany. Pomiń ten krok.
- W przeciwnym razie:
  1. Pobierz **Zadig** ze strony <https://zadig.akeo.ie/>.
  2. Podłącz i włącz laser.
  3. W Zadig wybierz menu **Options → List All Devices**.
  4. Z listy wybierz urządzenie **USB-EPP/I2C… CH341A** (ID `1A86 5512`).
  5. Po prawej stronie strzałki wybierz **libusb-win32**.
  6. Kliknij **Replace Driver** (lub **Install Driver**).

Uwaga: po tej zmianie LaserDRW i CorelLaser nie będą działać z laserem, bo
używają innego sterownika. Przywrócisz go w Menedżerze urządzeń (Aktualizuj
sterownik → Wybierz z listy).

Zamiast Zadig możesz też użyć instalatora sterownika od autora K40 Whisperer:
<https://github.com/scorchworks/K40-Whisperer-Driver-Installer>.

### 4. Kerfly

1. Rozpakuj paczkę `kerfly-….zip`, np. do `C:\Kerfly`.
2. Kliknij dwukrotnie **`start_kerfly.bat`**.
   - Pierwsze uruchomienie trwa kilka minut, bo instaluje biblioteki. Potrzebny
     jest internet.
   - Kolejne uruchomienia startują od razu.

## Linux (Debian / Ubuntu)

```bash
sudo apt install python3-venv inkscape
unzip kerfly-*.zip -d ~/Kerfly     # albo: git clone https://github.com/cyryllo/Kerfly
cd ~/Kerfly/kerfly-*
./start_kerfly.sh
```

### Dostęp do lasera bez roota (jednorazowo)

```bash
sudo groupadd -f lasercutter
sudo usermod -a -G lasercutter $USER
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5512", ENV{DEVTYPE}=="usb_device", MODE="0664", GROUP="lasercutter"' | sudo tee /etc/udev/rules.d/97-ctc-lasercutter.rules
```

Potem wyloguj się i zaloguj ponownie (albo uruchom komputer ponownie).

## Autotest

Przed pierwszym zadaniem sprawdź instalację. Podłącz i włącz laser, a potem
w folderze Kerfly uruchom:

- Windows (Wiersz polecenia, `cmd`): `start_kerfly.bat --self-test`
- Linux: `./start_kerfly.sh --self-test`

Kerfly wypisze po jednej linii na każde sprawdzenie: biblioteki, sterownik
USB, czy widzi laser (nie rusza nim), Inkscape, folder ustawień i czy okno
otwiera projekt. Linie `FAIL` trzeba naprawić. Linie `WARN` dotyczą rzeczy
opcjonalnych albo niepodłączonego lasera. Wynik dołącz do każdego zgłoszenia
błędu.

## Pierwszy test na laserze (lista kontrolna)

Kerfly wysyła do lasera te same dane co K40 Whisperer 0.71, co sprawdzają
testy. Sterowanie maszyną (połączenie, ruchy, pauza) sprawdzamy jednak na
sprzęcie po raz pierwszy. Trzymaj rękę przy wyłączniku lasera.

1. **Ustawienia → Maszyna**: wybierz swoją płytę (np. LASER-M2 albo M3),
   wymiary stołu i jednostki.
2. Zakładka **Laser → Połącz** (ikona wtyczki). Głowica powinna zjechać do
   pozycji bazowej (lewy górny róg).
3. **Strzałki**: przesuń głowicę o 10 mm w każdą stronę. Sprawdź, czy kierunki
   się zgadzają.
4. Otwórz prosty projekt (np. narysuj prostokąt 20×20 mm).
5. **Objazd konturu** (ikona ramki obok Start) przy wyłączonym laserze albo
   zamkniętej osłonie. Głowica powinna objechać prostokąt w miejscu, które
   widzisz na podglądzie.
6. Małe cięcie przy **niskiej mocy** na skrawku materiału.
7. W trakcie zadania sprawdź **Pauzę** (zatrzymuje się, drugie kliknięcie
   wznawia) i **Stop** (kończy od razu).
8. Jeśli coś zachowa się inaczej niż w K40 Whisperer, zapisz, co dokładnie
   zrobiłeś. Oryginalne okno K40 Whisperer też jest w paczce i korzysta z tego
   samego środowiska. Uruchomisz je w folderze Kerfly poleceniem
   `.venv\Scripts\python k40_whisperer.py` (Windows) albo
   `.venv/bin/python k40_whisperer.py` (Linux, wymaga `python3-tk`).

## Gdy coś nie działa

- **„USB error … libUSB driver not installed”**: brakuje sterownika (krok 3
  dla Windows) albo reguły udev (Linux).
- **Pliki SVG się nie otwierają**: zainstaluj Inkscape albo wskaż go w
  Ustawienia → Zaawansowane.
- **Windows: „Python was not found”**: zainstaluj Pythona z zaznaczoną opcją
  „Add python.exe to PATH”.
