#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ============================================================
#   BET ANALYZER - Analizator zakładów piłkarskich z AI
#   Wymaga: pip install requests openai colorama
# ============================================================

import requests
import time
import json
from colorama import Fore, Style, init
from openai import OpenAI

init(autoreset=True)

# ===================== TWOJE KLUCZE API =====================
FOOTBALL_API_KEY = "TUTAJ_WKLEJ_KLUCZ_API_FOOTBALL"   # -> api-sports.io (darmowy)
OPENAI_API_KEY   = "TUTAJ_WKLEJ_KLUCZ_OPENAI"          # -> platform.openai.com

POLLING          = 60          # sekund między analizami
MODEL            = "gpt-4o-mini"
HEADERS          = {"x-apisports-key": FOOTBALL_API_KEY}
API_URL          = "https://v3.football.api-sports.io"
client           = OpenAI(api_key=OPENAI_API_KEY)

# ==================== POBIERANIE DANYCH ====================

def api_get(endpoint, params={}):
    """Pobiera dane z API-Football."""
    try:
        r = requests.get(f"{API_URL}/{endpoint}", headers=HEADERS, params=params, timeout=10)
        return r.json().get("response", [])
    except Exception as e:
        print(Fore.RED + f"  [BŁĄD API] {e}")
        return []


def pobierz_mecze():
    """Pobiera mecze live, a jeśli brak – najbliższe."""
    print(Fore.CYAN + "  Szukam meczów live...")
    mecze = api_get("fixtures", {"live": "all"})
    if not mecze:
        print(Fore.YELLOW + "  Brak live. Pobieram najbliższe mecze...")
        mecze = api_get("fixtures", {"next": 20})
    return mecze


def formatuj_liste(mecze):
    """Formatuje surowe dane meczów do prostej listy."""
    lista = []
    for i, m in enumerate(mecze[:20]):
        f  = m["fixture"]
        t  = m["teams"]
        g  = m["goals"]
        lista.append({
            "nr":        i + 1,
            "id":        f["id"],
            "home":      t["home"]["name"],
            "away":      t["away"]["name"],
            "home_id":   t["home"]["id"],
            "away_id":   t["away"]["id"],
            "gole_h":    g["home"],
            "gole_a":    g["away"],
            "liga":      m["league"]["name"],
            "minuta":    f["status"]["elapsed"],
            "status":    f["status"]["short"],
        })
    return lista


def pobierz_statystyki(fid):
    return api_get("fixtures/statistics", {"fixture": fid})


def pobierz_h2h(h_id, a_id):
    return api_get("fixtures/headtohead", {"h2h": f"{h_id}-{a_id}", "last": 5})


def pobierz_forme(team_id):
    return api_get("fixtures", {"team": team_id, "last": 5, "status": "FT"})


def pobierz_aktualny_wynik(fid):
    dane = api_get("fixtures", {"id": fid})
    return dane[0] if dane else None


# ==================== BUDOWANIE KONTEKSTU ====================

def forma_str(mecze, team_id):
    """Zamienia ostatnie mecze na ciąg W/D/L."""
    wyniki = []
    for m in mecze:
        t, g = m["teams"], m["goals"]
        if t["home"]["id"] == team_id:
            wyniki.append("W" if g["home"] > g["away"] else ("D" if g["home"] == g["away"] else "L"))
        else:
            wyniki.append("W" if g["away"] > g["home"] else ("D" if g["away"] == g["home"] else "L"))
    return " ".join(wyniki) if wyniki else "brak danych"


def zbierz_dane(mecz, kurs):
    """Pobiera wszystkie dane i buduje tekst dla AI."""
    fid, h_id, a_id = mecz["id"], mecz["home_id"], mecz["away_id"]

    print(Fore.CYAN + "  Pobieram statystyki meczu...")
    stats = pobierz_statystyki(fid)

    print(Fore.CYAN + "  Pobieram historię H2H...")
    h2h = pobierz_h2h(h_id, a_id)

    print(Fore.CYAN + "  Pobieram formę drużyn...")
    f_h = forma_str(pobierz_forme(h_id), h_id)
    f_a = forma_str(pobierz_forme(a_id), a_id)

    # Aktualny wynik
    live = pobierz_aktualny_wynik(fid)
    if live:
        g   = live["goals"]
        min = live["fixture"]["status"]["elapsed"] or "?"
        wynik_txt = f"{g['home']}-{g['away']} ({min}')"
    else:
        wynik_txt = f"{mecz['gole_h']}-{mecz['gole_a']} ({mecz['minuta'] or '?'}')"

    # Statystyki (possession, strzały, xG itp.)
    stat_txt = ""
    for ts in stats:
        stat_txt += f"\n{ts['team']['name']}:\n"
        for s in ts.get("statistics", []):
            if s["value"] not in [None, ""]:
                stat_txt += f"  {s['type']}: {s['value']}\n"

    # H2H
    h2h_txt = ""
    for m in h2h[-5:]:
        t, g = m["teams"], m["goals"]
        h2h_txt += f"  {t['home']['name']} {g['home']}-{g['away']} {t['away']['name']}\n"

    return wynik_txt, f"""
MECZ: {mecz['home']} vs {mecz['away']}
LIGA: {mecz['liga']}
AKTUALNY WYNIK: {wynik_txt}
KURS (podany przez użytkownika): {kurs}

FORMA OSTATNICH 5 MECZÓW:
  {mecz['home']}: {f_h}
  {mecz['away']}: {f_a}

BEZPOŚREDNIE SPOTKANIA (H2H):
{h2h_txt if h2h_txt else '  Brak danych H2H'}

STATYSTYKI MECZU (live):
{stat_txt if stat_txt else '  Brak statystyk – mecz może jeszcze nie trwać'}
""".strip()


# ==================== ANALIZA AI ====================

SYSTEM_PROMPT = """Jesteś ekspertem analizy sportowej i zakładów bukmacherskich.
Na podstawie podanych danych meczowych daj rekomendację bukmacherską.

Odpowiedz WYŁĄCZNIE w formacie JSON (bez żadnego markdown ani ```):
{
  "rekomendacja": "POSTAW" lub "CASH OUT TERAZ" lub "TRZYMAJ" lub "NIE RUSZAJ",
  "pewnosc": <liczba 0-100>,
  "powod": "<max 2 zdania po polsku>",
  "ryzyko": "NISKIE" lub "ŚREDNIE" lub "WYSOKIE"
}

Przy ocenie uwzględnij: formę drużyn (W/D/L), H2H, statystyki live (possession %, strzały,
celne strzały, xG jeśli dostępne), aktualny wynik i minutę meczu, podany kurs (wartość),
ryzyko remisu, prawdopodobieństwo over/under 2.5 gola, tempo i dynamikę meczu.
Kurs poniżej 1.30 = mała wartość. 1.30-1.80 = dobra. Powyżej 1.80 = ryzykowne."""


def analizuj_ai(dane_meczu):
    """Wysyła dane do GPT i zwraca słownik z analizą."""
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": dane_meczu},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        tekst = resp.choices[0].message.content.strip()
        return json.loads(tekst)
    except json.JSONDecodeError:
        return {"rekomendacja": "BŁĄD", "pewnosc": 0,
                "powod": "AI zwróciło niepoprawny format JSON.", "ryzyko": "WYSOKIE"}
    except Exception as e:
        return {"rekomendacja": "BŁĄD", "pewnosc": 0, "powod": str(e), "ryzyko": "WYSOKIE"}


# ==================== WYŚWIETLANIE ====================

KOLORY_REK = {
    "POSTAW":         Fore.GREEN,
    "CASH OUT TERAZ": Fore.YELLOW,
    "TRZYMAJ":        Fore.CYAN,
    "NIE RUSZAJ":     Fore.RED,
    "BŁĄD":           Fore.RED,
}

KOLORY_RYZYKO = {
    "NISKIE":  Fore.GREEN,
    "ŚREDNIE": Fore.YELLOW,
    "WYSOKIE": Fore.RED,
}


def wyswietl_wynik(mecz, analiza, wynik_txt):
    rek   = analiza.get("rekomendacja", "BŁĄD")
    ryzyko = analiza.get("ryzyko", "?")
    kolor = KOLORY_REK.get(rek, Fore.WHITE)
    kr    = KOLORY_RYZYKO.get(ryzyko, Fore.WHITE)

    linia = "=" * 58
    print(f"\n{Fore.CYAN + Style.BRIGHT}{linia}")
    print(Fore.CYAN + Style.BRIGHT +
          f"  ANALIZA: {mecz['home']} - {mecz['away']}")
    print(Fore.CYAN + Style.BRIGHT + linia)
    print(f"  Aktualny wynik : {Style.BRIGHT}{wynik_txt}")
    print(f"  Rekomendacja   : {kolor + Style.BRIGHT}{rek}")
    print(f"  Pewność        : {Fore.MAGENTA + Style.BRIGHT}{analiza.get('pewnosc', '?')}%")
    print(f"  Powód          : {Fore.WHITE}{analiza.get('powod', '-')}")
    print(f"  Ryzyko straty  : {kr + Style.BRIGHT}{ryzyko}")
    print(Fore.CYAN + Style.BRIGHT + linia)


# ==================== GŁÓWNA FUNKCJA ====================

def wybierz_mecz(lista):
    """Wyświetla listę meczów i pyta użytkownika o wybór."""
    print(Fore.CYAN + Style.BRIGHT + "\n  DOSTĘPNE MECZE:\n")
    for m in lista:
        if m["minuta"]:
            wynik = f"{m['gole_h']}-{m['gole_a']} ({m['minuta']}')"
        else:
            wynik = "wkrótce"
        print(f"  {Fore.YELLOW}{m['nr']:2}.{Style.RESET_ALL} "
              f"[{m['liga'][:25]}] "
              f"{m['home']} vs {m['away']}  |  {wynik}")

    while True:
        try:
            nr = int(input(Fore.YELLOW + "\nWybierz numer meczu: "))
            for m in lista:
                if m["nr"] == nr:
                    return m
            print(Fore.RED + "Zły numer. Spróbuj jeszcze raz.")
        except ValueError:
            print(Fore.RED + "Wpisz cyfrę!")


def main():
    print(Fore.GREEN + Style.BRIGHT + "\n" + "=" * 58)
    print(Fore.GREEN + Style.BRIGHT +
          "   BET ANALYZER - Analizator zakładów sportowych z AI")
    print(Fore.GREEN + Style.BRIGHT + "=" * 58)
    print(Fore.WHITE + "  Naciśnij Ctrl+C żeby wyjść w dowolnym momencie.\n")

    mecze_raw = pobierz_mecze()
    if not mecze_raw:
        print(Fore.RED + "\nBrak meczów lub błąd klucza API. Sprawdź FOOTBALL_API_KEY.")
        return

    lista = formatuj_liste(mecze_raw)
    wybrany = wybierz_mecz(lista)

    kurs = input(Fore.YELLOW +
                 f"\nPodaj aktualny kurs dla '{wybrany['home']} vs {wybrany['away']}': ")

    print(Fore.GREEN + f"\n  Śledzę mecz: {wybrany['home']} vs {wybrany['away']}")
    print(Fore.WHITE + f"  Analiza co {POLLING} sekund. Ctrl+C = wyjście.\n")

    try:
        while True:
            print(Fore.CYAN + "\n  Pobieram dane i analizuję...")
            wynik_txt, dane = zbierz_dane(wybrany, kurs)
            analiza = analizuj_ai(dane)
            wyswietl_wynik(wybrany, analiza, wynik_txt)
            print(Fore.WHITE +
                  f"\n  Następna analiza za {POLLING} sekund... (Ctrl+C = wyjście)")
            time.sleep(POLLING)
    except KeyboardInterrupt:
        print(Fore.GREEN + "\n\n  Do widzenia! Powodzenia z typami!\n")


if __name__ == "__main__":
    main()


# ============================================================
# ============================================================
#
#   INSTRUKCJE INSTALACJI I URUCHOMIENIA
#   (JAK DLA TOTALNEGO POCZĄTKUJĄCEGO – KROK PO KROKU)
#
# ============================================================
# ============================================================
#
# -------------------------------------------------------
# KROK 1: ZAINSTALUJ PYTHON
# -------------------------------------------------------
# 1. Otwórz przeglądarkę i wejdź na: https://www.python.org/downloads/
# 2. Kliknij duży żółty przycisk "Download Python 3.x.x"
#    (numer wersji nie ma znaczenia, byle 3.x)
# 3. Uruchom pobrany plik instalacyjny (np. python-3.x.x-amd64.exe)
# 4. NA PIERWSZYM EKRANIE KONIECZNIE zaznacz:
#       [x] Add Python to PATH
#    (bez tego nic nie zadziała!)
# 5. Kliknij "Install Now" i poczekaj.
# 6. Kliknij "Close" po zakończeniu.
#
# Sprawdzenie czy Python działa:
#   - Otwórz menu Start -> wpisz "cmd" -> wciśnij Enter
#   - Wpisz:  python --version
#   - Powinieneś zobaczyć np.:  Python 3.12.0
#   Jeśli widzisz błąd – odinstaluj i zainstaluj Pythona jeszcze raz,
#   pamiętając o zaznaczeniu "Add Python to PATH".
#
# -------------------------------------------------------
# KROK 2: ZAINSTALUJ VISUAL STUDIO CODE (VS CODE)
# -------------------------------------------------------
# 1. Wejdź na: https://code.visualstudio.com/
# 2. Kliknij "Download for Windows" (lub Mac/Linux)
# 3. Uruchom instalator – klikaj "Next" wszędzie, nic nie zmieniaj.
# 4. Przy opcji "Additional Tasks" zaznacz:
#       [x] Add "Open with Code" action to Windows Explorer...
#       [x] Add to PATH
# 5. Kliknij "Install" i poczekaj.
#
# -------------------------------------------------------
# KROK 3: ZDOBĄDŹ KLUCZ API DO DANYCH PIŁKARSKICH (darmowy)
# -------------------------------------------------------
# Użyjemy serwisu API-Sports (api-sports.io):
#
# 1. Wejdź na: https://dashboard.api-football.com/register
# 2. Zarejestruj się (imię, email, hasło) – bez karty kredytowej!
# 3. Po zalogowaniu kliknij na swój profil (góra strony) lub wejdź:
#    https://dashboard.api-football.com/
# 4. Znajdź sekcję "API Key" lub "My Account"
# 5. Skopiuj swój klucz API (ciąg liter i cyfr, np. "abc123def456...")
#
# WAŻNE: Darmowy plan = 100 zapytań dziennie.
# Każda analiza zużywa ok. 5-6 zapytań, więc masz na ok. 15-20 analiz.
#
# -------------------------------------------------------
# KROK 4: ZDOBĄDŹ KLUCZ OPENAI
# -------------------------------------------------------
# 1. Wejdź na: https://platform.openai.com/
# 2. Zaloguj się lub zarejestruj (potrzebujesz konta OpenAI)
# 3. Kliknij swój avatar (prawy górny róg) -> "API keys"
#    lub wejdź bezpośrednio: https://platform.openai.com/api-keys
# 4. Kliknij "+ Create new secret key"
# 5. Wpisz dowolną nazwę (np. "bet_analyzer") -> "Create"
# 6. NATYCHMIAST skopiuj klucz (zaczyna się od "sk-...")
#    Bo więcej go nie zobaczysz!
# 7. Wklej gdzieś w bezpieczne miejsce (np. Notatnik)
#
# WAŻNE: Masz tylko 2$ kredytu. Model gpt-4o-mini jest bardzo tani
# (ok. 0.15$ za milion tokenów wejściowych), więc 2$ wystarczy
# na setki analiz.
#
# -------------------------------------------------------
# KROK 5: STWÓRZ FOLDER PROJEKTU
# -------------------------------------------------------
# 1. Otwórz Eksplorator plików (folder żółty na pasku zadań)
# 2. Przejdź np. do C:\Users\TwojeImie\Dokumenty
# 3. Kliknij prawym przyciskiem myszy -> "Nowy folder"
# 4. Nazwij go:  bet_analyzer
#    (bez spacji, bez polskich znaków)
#
# -------------------------------------------------------
# KROK 6: OTWÓRZ FOLDER W VS CODE
# -------------------------------------------------------
# 1. Otwórz VS Code (z menu Start)
# 2. Kliknij: File -> Open Folder
# 3. Znajdź i wybierz folder "bet_analyzer" który właśnie stworzyłeś
# 4. Kliknij "Wybierz folder" (lub "Select Folder")
# 5. Jeśli VS Code zapyta "Do you trust the authors?" -> kliknij "Yes"
#
# -------------------------------------------------------
# KROK 7: STWÓRZ PLIK bet_analyzer.py
# -------------------------------------------------------
# 1. W VS Code kliknij ikonę "New File" (strona z plusem)
#    w panelu po lewej stronie (Explorer)
#    LUB: Ctrl+N (nowy plik) -> Ctrl+Shift+S (zapisz jako)
# 2. Nazwij plik:  bet_analyzer.py
#    (z rozszerzeniem .py – to ważne!)
# 3. Wklej CAŁY KOD z tego pliku (od początku aż do końca komentarzy)
# 4. Zapisz: Ctrl+S
#
# -------------------------------------------------------
# KROK 8: WKLEJ SWOJE KLUCZE API DO KODU
# -------------------------------------------------------
# W pliku bet_analyzer.py znajdź te dwie linie na górze:
#
#   FOOTBALL_API_KEY = "TUTAJ_WKLEJ_KLUCZ_API_FOOTBALL"
#   OPENAI_API_KEY   = "TUTAJ_WKLEJ_KLUCZ_OPENAI"
#
# Zamień tekst w cudzysłowach na swoje prawdziwe klucze, np.:
#
#   FOOTBALL_API_KEY = "abc123def456ghi789"
#   OPENAI_API_KEY   = "sk-proj-abcdef123456..."
#
# WAŻNE: Zostaw cudzysłowy! Klucz musi być w cudzysłowach!
# Zapisz plik po zmianach: Ctrl+S
#
# -------------------------------------------------------
# KROK 9: ZAINSTALUJ WYMAGANE PAKIETY
# -------------------------------------------------------
# 1. W VS Code otwórz terminal:
#    Kliknij: Terminal -> New Terminal
#    (lub: Ctrl+` – ten znak to backtick, klawisz obok 1)
# 2. Na dole ekranu pojawi się czarny pasek – to jest terminal
# 3. Wpisz dokładnie tę komendę i wciśnij Enter:
#
#       pip install requests openai colorama
#
# 4. Poczekaj chwilę – zobaczysz jak pakiety się pobierają.
# 5. Na końcu powinno się pokazać:
#       Successfully installed ...
#    Jeśli widzisz błąd "pip nie jest rozpoznawane jako polecenie":
#       Spróbuj: python -m pip install requests openai colorama
#
# -------------------------------------------------------
# KROK 10: URUCHOM PROGRAM
# -------------------------------------------------------
# 1. W terminalu VS Code (ten czarny pasek na dole) wpisz:
#
#       python bet_analyzer.py
#
# 2. Wciśnij Enter
# 3. Program powinien się uruchomić i wyświetlić:
#       BET ANALYZER - Analizator zakładów sportowych z AI
# 4. Postępuj zgodnie z instrukcjami na ekranie:
#    - Zobaczysz listę meczów
#    - Wpisz numer meczu który chcesz śledzić
#    - Wpisz aktualny kurs (np. 1.75)
#    - Program będzie analizował mecz co 60 sekund
# 5. Żeby zakończyć – wciśnij Ctrl+C
#
# -------------------------------------------------------
# NAJCZĘSTSZE BŁĘDY I ICH ROZWIĄZANIA
# -------------------------------------------------------
#
# BŁĄD: "ModuleNotFoundError: No module named 'requests'"
# LUB:  "ModuleNotFoundError: No module named 'openai'"
# LUB:  "ModuleNotFoundError: No module named 'colorama'"
# ROZWIĄZANIE: Nie zainstalowałeś pakietów. Uruchom w terminalu:
#       pip install requests openai colorama
#
# -------------------------------------------------------
# BŁĄD: "AuthenticationError" lub "Incorrect API key"
# ROZWIĄZANIE: Twój klucz OpenAI jest nieprawidłowy.
#   Sprawdź czy:
#   1. Wklejony klucz jest poprawny (zaczyna się od "sk-")
#   2. Jest w cudzysłowach: OPENAI_API_KEY = "sk-..."
#   3. Nie ma spacji przed ani po kluczu
#
# -------------------------------------------------------
# BŁĄD: "[BŁĄD API]" lub "Brak meczów lub błąd klucza API"
# ROZWIĄZANIE: Twój klucz API-Football jest nieprawidłowy
#   lub skończyły Ci się darmowe zapytania na dziś (100/dzień).
#   Sprawdź klucz na: https://dashboard.api-football.com/
#
# -------------------------------------------------------
# BŁĄD: "python nie jest rozpoznawane jako polecenie"
# ROZWIĄZANIE: Python nie jest dodany do PATH.
#   Odinstaluj Python (Panel Sterowania -> Programy)
#   i zainstaluj ponownie, pamiętając o:
#       [x] Add Python to PATH
#
# -------------------------------------------------------
# BŁĄD: Wszystko działa ale AI zwraca "BŁĄD"
# ROZWIĄZANIE: Sprawdź czy masz środki na koncie OpenAI.
#   Wejdź na: https://platform.openai.com/usage
#   Jeśli skończyły Ci się 2$, doładuj konto.
#
# -------------------------------------------------------
# WSKAZÓWKI DLA POCZĄTKUJĄCYCH:
# -------------------------------------------------------
#
# * Jeśli widzisz czerwony komunikat – to błąd. Czytaj go uważnie,
#   zwykle mówi ci co poszło nie tak.
#
# * Kod możesz edytować w VS Code – kliknij na plik bet_analyzer.py
#   w lewym panelu.
#
# * POLLING = 60 (sekund między analizami) możesz zmienić na mniejszą
#   wartość np. 30, ale pamiętaj – każda analiza = ok. 5-6 zapytań API
#   (limit: 100/dzień na darmowym koncie).
#
# * Aplikacja działa tylko dla PIŁKI NOŻNEJ (API-Football).
#   Dla tenisa, koszykówki i CS2 potrzebne byłyby inne API.
#
# * Jeśli chcesz zamknąć program – zawsze używaj Ctrl+C.
#   Nie zamykaj okna terminala na krzyżyk podczas działania programu.
#
# -------------------------------------------------------
# To wszystko! Powodzenia i dobre typy!
# -------------------------------------------------------
