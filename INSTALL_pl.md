# Kerfly: instalacja

Opis programu po polsku jest w [README_pl.md](README_pl.md).

Kerfly ma dwie gotowe paczki. Pobierz tę dla swojego systemu ze
[strony wydań](https://github.com/cyryllo/Kerfly/releases/latest). Nic więcej
nie jest potrzebne.

## Windows 10 / 11: instalator

1. Pobierz **`Kerfly-<wersja>-windows-setup.exe`**.
2. Podłącz kabel USB lasera i włącz laser.
3. Uruchom instalator. Windows może pokazać **„System Windows ochronił ten
   komputer”**: instalator nie jest podpisany (certyfikat do podpisu jest
   płatny), więc Windows nie zna wydawcy. Wybierz **Więcej informacji →
   Uruchom mimo to**.
4. Za pierwszym razem zaznacz **„Zainstaluj sterownik USB lasera K40”**.
   Instaluje on sterownik libusb-win32, którego potrzebuje laser. Jeśli
   Kerfly albo inny program do tego lasera już z nim działał na tym
   komputerze, sterownik jest i możesz tego nie zaznaczać. Po zmianie
   sterownika LaserDRW i CorelLaser nie będą działać z laserem.
5. Uruchom Kerfly z menu Start (albo ikoną na pulpicie, jeśli ją wybrałeś).

## Linux: AppImage

1. Pobierz **`Kerfly-<wersja>-x86_64.AppImage`**.
2. Nadaj mu prawo uruchamiania: w menedżerze plików Właściwości → Zezwól na
   uruchamianie jako program, albo w terminalu:

   ```bash
   chmod +x Kerfly-*.AppImage
   ```

3. Uruchom AppImage (dwuklik albo `./Kerfly-*.AppImage`).
4. Daj swojemu użytkownikowi dostęp do portu USB lasera, raz na komputer.
   Najprościej: w Kerfly wybierz **Laser → Zezwól na dostęp do USB
   lasera…**. System raz zapyta o hasło; potem odłącz kabel USB lasera i
   podłącz go ponownie. (Kerfly sam to zaproponuje, gdy nie może się połączyć
   z braku uprawnień.)

   Albo ręcznie w terminalu, a potem wyloguj się i zaloguj ponownie:

   ```bash
   sudo groupadd -f lasercutter
   sudo usermod -a -G lasercutter $USER
   echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5512", ENV{DEVTYPE}=="usb_device", MODE="0664", GROUP="lasercutter"' | sudo tee /etc/udev/rules.d/97-ctc-lasercutter.rules
   ```

   Sama grupa `dialout` nie wystarczy: płyta lasera nie jest portem
   szeregowym.

## Autotest

Przed pierwszym zadaniem sprawdź instalację. Podłącz i włącz laser, a potem
uruchom w wierszu poleceń (Windows) albo w terminalu (Linux):

- Windows: `"C:\Program Files\Kerfly\kerfly-console.exe" --self-test`
- Linux: `./Kerfly-<wersja>-x86_64.AppImage --self-test`

Kerfly wypisze po jednej linii na każde sprawdzenie: biblioteki, sterownik
USB, czy widzi laser (nie rusza nim), Inkscape, folder ustawień i czy okno
otwiera projekt. Linie `FAIL` trzeba naprawić. Linie `WARN` dotyczą rzeczy
opcjonalnych albo niepodłączonego lasera.

## Pierwsze uruchomienie z laserem

Trzymaj rękę przy wyłączniku lasera.

1. **Ustawienia → Maszyna**: wybierz swoją płytę (np. LASER-M2 albo M3),
   wymiary stołu i jednostki.
2. Zakładka **Laser → Połącz** (ikona wtyczki). Głowica zjedzie do pozycji
   bazowej (lewy górny róg).
3. Przesuń głowicę strzałkami i sprawdź, czy kierunki się zgadzają.
4. Narysuj prostokąt 20 × 20 mm i uruchom **Objazd konturu** przy wyłączonym
   laserze.
5. Zrób małe cięcie przy niskiej mocy na skrawku materiału. Sprawdź **Pauzę**
   (drugie kliknięcie wznawia) i **Stop**.

Resztę opisuje [instrukcja obsługi](https://cyryllo.github.io/Kerfly/pl/guide.html).

## Gdy coś nie działa

- **„Błąd USB … sterownik libUSB nie jest zainstalowany”**: na Windows
  uruchom instalator jeszcze raz i zaznacz sterownik USB; na Linuksie wybierz
  **Laser → Zezwól na dostęp do USB lasera…** (krok 4), potem podłącz laser
  ponownie.
- **Brakuje tekstu z SVG albo nie jest cięty**: zainstaluj
  [Inkscape](https://inkscape.org/release/) (opcjonalny). Kerfly otwiera pliki
  SVG sam, ale do zamiany tekstu z SVG na linie potrzebuje Inkscape. Kerfly
  sam go znajdzie, a jeśli nie, wskaż go w Ustawienia → Zaawansowane.

Żeby zgłosić problem, wybierz **Pomoc → Zgłoś problem na GitHubie…** (albo
przycisk **Zgłoś błąd**). Kerfly zapisze raport diagnostyczny i otworzy
formularz zgłoszenia na GitHubie z wpisaną wersją, systemem i płytą.
Przeciągnij plik raportu do pola „Diagnostic report”. Do wysłania potrzebne
jest darmowe konto GitHub. Formularz jest po angielsku, ale zgłoszenie można
napisać po polsku.

---

Uruchamianie ze źródeł, budowanie paczek i testy:
[DEVELOPMENT.md](DEVELOPMENT.md) (po angielsku).
