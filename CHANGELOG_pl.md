# Lista zmian Kerfly (po polsku)

Polska wersja opisów wydań, od 1.4.0. Pełna historia jest w
[CHANGELOG.md](CHANGELOG.md) (po angielsku).

## Unreleased

### Dodane

- **Moc objazdu konturu z włączonym laserem**: Ustawienia → Wektory, zaraz pod
  *Objazd konturu z włączonym laserem* (wyszarzona, gdy ta opcja jest
  wyłączona), w procentach mocy maksymalnej. Płyta M3 dostaje ją podczas
  objazdu; na innych płytach moc ustawia jak dotąd pokrętło lasera.
- **Raport po zadaniu** (Ustawienia → Maszyna, domyślnie włączony): małe okno
  z czasem zadania, które czeka, aż wrócisz do lasera (nie blokuje Kerfly).
  Nie pojawia się po objeździe konturu.
- **Uruchom program po zadaniu** (Ustawienia → Maszyna): program albo skrypt
  (.bat, .sh) uruchamiany po każdym skończonym zadaniu, np. żeby wyłączyć
  wyciąg albo wysłać wiadomość; jego wynik i błędy są pokazane w raporcie
  (błędy także przy wyłączonym raporcie).

### Zmienione

- Ustawienia → Oś obrotowa: współczynnik skali i prędkość szybkich ruchów są
  wyszarzone, gdy oś obrotowa jest wyłączona (tak jak moc objazdu bez
  włączonego lasera).

## 1.4.1 (2026-11-13)

Poprawki: pieczątka na Windows, materiały z więcej niż trzema warstwami,
wyśrodkowane przyciski Tylko grawer/obrys/cięcie.

### Poprawione

- **Pieczątka na Windows: paski w 1.4.0 nadal były.** Tekst jest teraz
  rysowany jako wypełnione kontury liter, a nie przez systemowy mechanizm
  rysowania tekstu, więc wychodzi tak samo na Windows, Linuksie i macOS (razem z
  pogrubieniem, kursywą, podkreśleniem i rozmiarami z edytora pieczątki). Gdy
  lista czcionek jest pusta, Windows używa Ariala.
- **Zapis materiału z obecnych warstw zapisywał tylko trzy podstawowe
  warstwy.** Dodatkowe warstwy (drugie cięcie, kolejny grawer…) zapisują się z
  nazwą, kolorem, prędkością, przejściami, mocą i szerokością cięcia, są
  widoczne w oknie materiałów w części *Inne warstwy* (każdą można zmienić albo
  usunąć) i tworzą się z powrotem po zastosowaniu materiału.
- Kolorowy kwadrat i napis na przyciskach Tylko grawer, Tylko obrys i Tylko
  cięcie są wyśrodkowane (przylegały do lewej krawędzi).

## 1.4.0 (2026-11-13)

Kopiuj i wklej, menu pod prawym przyciskiem, edytor tekstu pieczątki, pudełka
dopasowane do stołu, pochodzenie każdego projektu i sprawdzanie nowych wersji.

### Poprawione

- **Pieczątka: paski w literach i przerywana ramka na Windows** (w podglądzie,
  w symulacji i przy grawerowaniu). Pieczątka jest teraz rysowana w zwykłym kolorowym
  obrazie i dopiero potem zamieniana na czerń i biel, a gdy brakuje czcionki
  DejaVu Sans (na Windows), używany jest Arial zamiast sztucznie pogrubionej
  zastępczej.
- **Symulacja otwierała się podwójnie** po drugim kliknięciu; teraz drugie
  kliknięcie przywołuje otwarte okno.
- **Linux AppImage: pliki SVG nie otwierały się, gdy zainstalowany jest
  Inkscape** (program się zawieszał). Programy uruchamiane przez Kerfly
  (Inkscape, przeglądarka) dostawały biblioteki z AppImage i Inkscape padał na
  starszej bibliotece C++; teraz dostają systemowe.

### Nowe

- **Nowe wersje:** raz dziennie przy starcie Kerfly pyta GitHuba, czy wyszła
  nowa wersja (nic o Tobie ani o Twojej pracy nie jest wysyłane). Pasek nad
  stołem pokazuje ją wtedy z przyciskami **Zobacz wydanie**, **Później** i
  **Pomiń tę wersję**. **Pomoc → Sprawdź aktualizacje** (na pasku
  **Aktualizacje**) sprawdza od razu. Domyślnie włączone; wyłączysz w
  Ustawienia → Zaawansowane. Kerfly niczego sam nie pobiera ani nie instaluje.
- **Kopiuj, wytnij i wklej** jak w Inkscape: Ctrl+C, Ctrl+X, Ctrl+V (wkleja pod
  kursorem, gdy jest nad stołem, inaczej 5 mm dalej), Ctrl+Alt+V wkleja w
  miejscu; także do innego projektu w tym samym oknie (grupy zostają grupami,
  warstwy idą po nazwie). **Zaznacz wszystko** (Ctrl+A) i **Odznacz** (Esc na
  stole, Ctrl+Shift+A). W menu Edycja i w nowej grupie **Schowek** na pasku,
  razem z Duplikuj i Usuń.
- **Tylko grawer, Tylko obrys, Tylko cięcie**: jeden rodzaj pracy naraz (np.
  grawer, sprawdzenie, potem cięcie); każdy wykonuje wszystkie zaznaczone
  warstwy swojego rodzaju z ich ustawieniami. Małe przyciski nad Start, zawsze
  widoczne także na małym ekranie, włączane w Ustawienia → Widok (domyślnie
  wyłączone); są też w menu Laser. Podpowiedź pokazuje czas ich części.
- **Skąd pochodzi każdy projekt:** lista elementów pokazuje otwarty plik razem
  z folderem (Klient A › projekt.svg), a dolny pasek foldery i plik projektu
  pod kursorem (albo zaznaczonego), pełną ścieżkę w podpowiedzi; projekty o
  tej samej nazwie z różnych folderów (folder na każdego klienta) łatwo
  odróżnić. Zapisane projekty, kopie i części rozbitego pliku pamiętają, skąd
  pochodzą.
- **Edytor tekstu pieczątki**: tekst pieczątki prostokątnej piszesz w małym
  edytorze, który od razu pokazuje go tak, jak będzie wyglądał: **B**
  pogrubienie, **I** kursywa, **U** podkreślenie, **A+ / A−** większe i
  mniejsze litery, wyrównanie wierszy, dla każdego fragmentu tekstu (np.
  nazwa duża i pogrubiona, adres mniejszy).
- **Pudełko na wczepy dopasowane do stołu**: części są układane w obszarze
  roboczym; te, które się nie mieszczą, trafiają na kolejny arkusz w tym samym
  miejscu, na własnej odhaczonej warstwie cięcia (Arkusz 2, …). Opcja **Każda
  część na osobnej warstwie**.
- **Puzzle z okrągłymi wypustkami**: wąska szyjka i okrągła główka, każda
  wypustka trochę inna.
- **Bazowanie głowicy po zadaniu** (Ustawienia → Maszyna): po skończonym
  zadaniu głowica wraca do 0, 0, gotowa na kolejną sztukę, bez naciskania
  Bazowanie (nie po Stopie i nie po objeździe konturu). Projekt zostaje na
  miejscu; następny Start podjeżdża do niego głowicą.
- **Menu pod prawym przyciskiem** na stole (kliknięcie bez przeciągania;
  przeciąganie prawym przyciskiem dalej przesuwa widok). Na elemencie: jego
  polecenia, z **Warstwa ▸**, która jednym kliknięciem przenosi wszystkie
  zaznaczone elementy na inną warstwę (np. każdy projekt na osobną warstwę
  grawera, zgłoszenie #2), łączenie kształtów, kolejność, wyrównanie, obrót,
  odbicie, wypełnienie, edycja węzłów, **Pomiń w zadaniu**. Na pustym stole:
  **Przesuń głowicę tutaj** (projekt zostaje na miejscu), wklej, zaznacz
  wszystko, dopasuj widok, siatka.
