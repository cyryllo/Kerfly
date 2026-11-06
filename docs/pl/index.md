---
layout: default
lang: pl
title: Kerfly po polsku
other_lang: index.html
description: Kerfly to darmowy program do sterowania laserami CO2 K40 z płytami Lihuiyu M2 Nano. Rysuj, układaj i tnij w Linuksie i Windows.
---

<div class="hero">
  <img src="{{ '/assets/logo.svg' | relative_url }}" alt="Logo Kerfly">
  <div>
    <h1>Kerfly</h1>
    <p>Darmowy program do sterowania laserami K40, dla Linuksa i Windows.</p>
  </div>
</div>

<div class="buttons">
  <a class="button primary" href="{{ site.repo }}/releases/latest">Pobierz (Windows, Linux)</a>
  <a class="button" href="{{ '/pl/guide.html' | relative_url }}">Instrukcja obsługi</a>
  <a class="button" href="{{ site.repo }}/blob/main/INSTALL_pl.md">Instalacja</a>
</div>

<div class="shot"><img src="{{ '/screenshot_pl.png' | relative_url }}" alt="Główne okno Kerfly z rysunkiem na stole lasera"></div>

Kerfly steruje laserami CO2 klasy K40 z **płytami Lihuiyu** (rodzina M2 Nano:
M1, M2, M3, B1, …), czyli popularnymi niebiesko-białymi laserami biurkowymi
sprzedawanymi pod wieloma nazwami. Rysujesz, układasz i uruchamiasz zadania
w jednym oknie, od pierwszego szkicu do wyciętej części.

## Co potrafi

<div class="features">
  <div class="feature"><h3>Układanie na stole</h3><p>Kilka plików naraz na stole lasera: przesuwanie, skalowanie i obracanie myszą albo wpisanymi wartościami, wyrównywanie, grupowanie i kolejność. Cofanie i ponawianie wszystkiego.</p></div>
  <div class="feature"><h3>Rysowanie i edycja</h3><p>Prostokąty, elipsy, wielokąty, linie, krzywe, rysowanie odręczne i tekst dowolną zainstalowaną czcionką, także wzdłuż krzywej albo okręgu. Edycja węzłów narysowanych kształtów i otwartych plików SVG oraz DXF.</p></div>
  <div class="feature"><h3>Warstwy jak w LightBurnie</h3><p>Grawer rastrowy, obrys i cięcie, każde z własną prędkością, liczbą przejść i mocą. Baza materiałów ustawia wszystko jednym wyborem.</p></div>
  <div class="feature"><h3>Wiele formatów</h3><p>SVG (z Inkscape albo bez), DXF, G-code i obrazy: PNG, JPG, BMP, TIFF, GIF, WebP. Projekt trzyma wszystko w jednym pliku.</p></div>
  <div class="feature"><h3>Wzory, zawiasy, mostki</h3><p>Wypełnianie kształtów grawerowanymi wzorami (fale, plaster miodu, cegły…), a ich obrys nadal jest cięty; zawiasy giętkie, dzięki którym sklejka się wygina; mostki trzymające wycięte elementy w arkuszu; łączenie kształtów.</p></div>
  <div class="feature"><h3>Bezpieczna praca</h3><p>Najpierw objazd konturu, symulacja zadania, szacowany czas. Kerfly nie wyśle zadania, które wyprowadziłoby głowicę poza stół.</p></div>
  <div class="feature"><h3>Twój sposób pracy</h3><p>Projekt może zostać na swoim miejscu na stole, a głowica do niego podjedzie, albo podążać za głowicą: wybór należy do Ciebie.</p></div>
  <div class="feature"><h3>Po polsku</h3><p>Polski, angielski, niemiecki, hiszpański i francuski. Działa w Windows 10 / 11 (instalator) i Linuksie (AppImage, większość dystrybucji).</p></div>
</div>

## Jak zacząć

Otwórz <a href="{{ site.repo }}/releases/latest">najnowsze wydanie</a> i pobierz paczkę dla swojego systemu. Python nie jest potrzebny.

<ol class="steps">
  <li><strong>Windows 10 / 11:</strong> uruchom <code>Kerfly-&lt;wersja&gt;-windows-setup.exe</code>. Instalator nie jest podpisany, więc Windows może pokazać <em>System Windows ochronił ten komputer</em>: wybierz <em>Więcej informacji → Uruchom mimo to</em>. Za pierwszym razem zaznacz <em>Zainstaluj sterownik USB lasera K40</em>. Kerfly będzie w menu Start.</li>
  <li><strong>Linux:</strong> nadaj plikowi <code>Kerfly-&lt;wersja&gt;-x86_64.AppImage</code> prawo uruchamiania i uruchom go. Raz dodaj <a href="{{ site.repo }}/blob/main/INSTALL_pl.md#linux-appimage">regułę dla portu USB lasera</a> (trzy polecenia).</li>
  <li>Przeczytaj <a href="{{ '/pl/guide.html' | relative_url }}">instrukcję obsługi</a>: połącz laser, ułóż projekt, objedź kontur, start.</li>
</ol>

<a href="{{ site.repo }}/blob/main/INSTALL_pl.md">Instrukcja instalacji</a> opisuje każdy krok.

## Stan projektu

**Kerfly 1.0 jest wersją stabilną, gotową do codziennej pracy** z laserem.
Następne w planach: wektoryzacja obrazów, więcej wzorów,
kompensacja kerfu, więcej formatów plików oraz paczka dla Debiana z własnym
repozytorium APT. Zobacz [plan]({{ site.repo }}/blob/main/ROADMAP.md) (po angielsku) i
[listę zmian]({{ site.repo }}/blob/main/CHANGELOG.md).

## Pomoc i uwagi

Coś nie działa? W Kerfly wybierz **Pomoc → Zgłoś problem na GitHubie…**:
program zapisze raport diagnostyczny i otworzy
[formularz zgłoszenia]({{ site.repo }}/issues/new/choose). Formularze są po
angielsku, ale **możesz pisać po polsku**. Pomysły i poprawki tłumaczeń też
są mile widziane.
