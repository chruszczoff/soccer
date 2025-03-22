import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session
import json
import os

# Twój klucz API
API_KEY = "3720c6cadb21e814adcc6295ef4b91b1"

BASE_URL = "https://v3.football.api-sports.io/"
LEAGUE_IDS = {
    "Premier League": 39,      # Anglia
    "La Liga": 140,            # Hiszpania
    "Ekstraklasa": 106,        # Polska
    "Serie A": 135,            # Włochy
    "Bundesliga": 78,          # Niemcy
    "Ligue 1": 61,             # Francja
    "UEFA Nations League": 5   # Liga Narodów UEFA
}

app = Flask(__name__)
app.secret_key = "super_tajny_klucz"  # Zmień na coś swojego
PASSWORD = "typertest123."  # Zmień na własne hasło
DATA_FILE = "predictions.json"

def get_team_id(team_name, league_id):
    headers = {"x-apisports-key": API_KEY}
    url = f"{BASE_URL}teams?league={league_id}&season=2024&name={team_name}"
    response = requests.get(url, headers=headers)
    data = response.json()
    if data["response"]:
        return data["response"][0]["team"]["id"]
    return None

def get_last_5_matches(team_name, league_id):
    team_id = get_team_id(team_name, league_id)
    headers = {"x-apisports-key": API_KEY}
    url = f"{BASE_URL}fixtures?team={team_id}&last=5"
    response = requests.get(url, headers=headers)
    return response.json()["response"]

def get_h2h_matches(team1_name, team2_name, league_id):
    team1_id = get_team_id(team1_name, league_id)
    team2_id = get_team_id(team2_name, league_id)
    headers = {"x-apisports-key": API_KEY}
    url = f"{BASE_URL}fixtures/headtohead?team1={team1_id}&team2={team2_id}&last=5"
    response = requests.get(url, headers=headers)
    return response.json()["response"]

def get_team_stats(team_name, league_id):
    team_id = get_team_id(team_name, league_id)
    headers = {"x-apisports-key": API_KEY}
    url = f"{BASE_URL}teams/statistics?league={league_id}&season=2024&team={team_id}"
    response = requests.get(url, headers=headers)
    data = response.json()["response"]
    is_international = league_id == 5  # Tylko UEFA NL
    
    home_wins = data["fixtures"]["wins"]["home"]
    away_wins = data["fixtures"]["wins"]["away"]
    goals_for = data["goals"]["for"]["total"]
    goals_against = data["goals"]["against"]["total"]
    
    if isinstance(home_wins, dict):  # Dla lig klubowych
        home_wins = home_wins["total"] if home_wins["total"] is not None else 0
        away_wins = away_wins["total"] if away_wins["total"] is not None else 0
        goals_for = goals_for["total"] if goals_for["total"] is not None else 0
        goals_against = goals_against["total"] if goals_against["total"] is not None else 0
    else:  # Dla rozgrywek międzynarodowych
        home_wins = home_wins if home_wins is not None else 0
        away_wins = away_wins if away_wins is not None else 0
        goals_for = (goals_for["home"] + goals_for["away"]) if goals_for else 0
        goals_against = (goals_against["home"] + goals_against["away"]) if goals_against else 0

    return {
        "position": 1 if is_international else (int(data["rank"]) if data.get("rank") else 20),
        "goals_for": goals_for,
        "goals_against": goals_against,
        "home_wins": home_wins,
        "away_wins": away_wins
    }

def calculate_form(matches):
    points = 0
    for match in matches:
        home_goals = match["goals"]["home"]
        away_goals = match["goals"]["away"]
        if home_goals is None or away_goals is None:
            continue
        if home_goals > away_goals:
            points += 3 if match["teams"]["home"]["winner"] else 0
        elif home_goals < away_goals:
            points += 3 if match["teams"]["away"]["winner"] else 0
        else:
            points += 1
    return points

def calculate_h2h(h2h_matches, team1_name):
    points = 0
    for match in h2h_matches:
        home_team = match["teams"]["home"]["name"]
        home_goals = match["goals"]["home"]
        away_goals = match["goals"]["away"]
        if home_goals is None or away_goals is None:
            continue
        if home_goals > away_goals:
            points += 3 if home_team == team1_name else 0
        elif home_goals < away_goals:
            points += 3 if home_team != team1_name else 0
        else:
            points += 1
    return points

def calculate_position_points(position):
    return max(20 - position + 1, 1)

def calculate_goal_diff(goals_for, goals_against):
    diff = goals_for - goals_against
    return max(min(diff // 5, 10), -10)

def calculate_home_away_points(stats, is_home_team):
    return min(stats["home_wins"] * 2, 10) if is_home_team else min(stats["away_wins"] * 2, 10)

def predict_winner(team1, team2, league_name, match_date):
    league_id = LEAGUE_IDS[league_name]
    matches1 = get_last_5_matches(team1, league_id)
    matches2 = get_last_5_matches(team2, league_id)
    if not matches1 or not matches2:
        return None
    form1 = calculate_form(matches1)
    form2 = calculate_form(matches2)
    h2h_matches = get_h2h_matches(team1, team2, league_id)
    h2h1 = calculate_h2h(h2h_matches, team1)
    h2h2 = calculate_h2h(h2h_matches, team2)
    stats1 = get_team_stats(team1, league_id)
    stats2 = get_team_stats(team2, league_id)
    pos1 = calculate_position_points(stats1["position"])
    pos2 = calculate_position_points(stats2["position"])
    goal_diff1 = calculate_goal_diff(stats1["goals_for"], stats1["goals_against"])
    goal_diff2 = calculate_goal_diff(stats2["goals_for"], stats2["goals_against"])
    home_away1 = calculate_home_away_points(stats1, True)
    home_away2 = calculate_home_away_points(stats2, False)
    total1 = form1 + h2h1 + pos1 + goal_diff1 + home_away1
    total2 = form2 + h2h2 + pos2 + goal_diff2 + home_away2
    prediction = team1 if total1 > total2 else team2 if total2 > total1 else "Remis"
    return {
        "match": f"{team1} vs {team2}",
        "team1_stats": f"Forma={form1}, H2H={h2h1}, Pozycja={pos1}, Bramki={goal_diff1}, Dom/Wyjazd={home_away1}, Łącznie={total1}",
        "team2_stats": f"Forma={form2}, H2H={h2h2}, Pozycja={pos2}, Bramki={goal_diff2}, Dom/Wyjazd={home_away2}, Łącznie={total2}",
        "prediction": prediction,
        "match_date": match_date,
        "league": league_name
    }

def get_upcoming_matches(league_name):
    league_id = LEAGUE_IDS[league_name]
    start_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")  # Jutro: 2025-03-23
    season = "2024"
    headers = {"x-apisports-key": API_KEY}
    url = f"{BASE_URL}fixtures?league={league_id}&season={season}&date={start_date}"
    response = requests.get(url, headers=headers)
    data = response.json()
    print(f"League: {league_name}, Date: {start_date}, Season: {season}, URL: {url}")
    print(f"API Response: {data}")
    if not data["response"]:
        print(f"No matches found for {league_name} on {start_date}")
    return data["response"]

def save_prediction(prediction):
    data = {}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
    match_id = f"{prediction['match_date']}_{prediction['match']}"
    data[match_id] = prediction
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def update_results():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
    for match_id, pred in data.items():
        if "result" not in pred:
            date = pred.get("match_date", pred.get("date"))
            league_id = LEAGUE_IDS[pred["league"]]
            headers = {"x-apisports-key": API_KEY}
            url = f"{BASE_URL}fixtures?league={league_id}&season=2024&date={date}"
            response = requests.get(url, headers=headers)
            fixtures = response.json()["response"]
            for fixture in fixtures:
                if f"{fixture['teams']['home']['name']} vs {fixture['teams']['away']['name']}" == pred["match"]:
                    home_goals = fixture["goals"]["home"]
                    away_goals = fixture["goals"]["away"]
                    if home_goals is not None and away_goals is not None:
                        result = fixture["teams"]["home"]["name"] if home_goals > away_goals else fixture["teams"]["away"]["name"] if away_goals > home_goals else "Remis"
                        pred["result"] = result
                    break
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)
    return data

def calculate_accuracy(data):
    accuracies = {league: {"correct": 0, "total": 0} for league in LEAGUE_IDS.keys()}
    accuracies["Overall"] = {"correct": 0, "total": 0}
    for pred in data.values():
        if "result" in pred:
            league = pred["league"]
            accuracies[league]["total"] += 1
            accuracies["Overall"]["total"] += 1
            if pred["prediction"] == pred["result"]:
                accuracies[league]["correct"] += 1
                accuracies["Overall"]["correct"] += 1
    for key in accuracies:
        total = accuracies[key]["total"]
        correct = accuracies[key]["correct"]
        accuracies[key]["percent"] = (correct / total * 100) if total > 0 else 0
    return accuracies

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["password"] == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Nieprawidłowe hasło")
    return render_template("login.html", error=None)

@app.route("/index")
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    predictions_by_league = {}
    for league in LEAGUE_IDS.keys():
        matches = get_upcoming_matches(league)
        if matches:
            predictions_by_league[league] = []
            for match in matches:
                team1 = match["teams"]["home"]["name"]
                team2 = match["teams"]["away"]["name"]
                match_date = match["fixture"]["date"].split("T")[0]
                prediction = predict_winner(team1, team2, league, match_date)
                if prediction:
                    save_prediction(prediction)
                    predictions_by_league[league].append(prediction)
        else:
            predictions_by_league[league] = None
    
    data = update_results()
    accuracies = calculate_accuracy(data)
    
    return render_template("index.html", predictions_by_league=predictions_by_league, accuracies=accuracies)

@app.route("/stats")
def stats():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    data = update_results()
    accuracies = calculate_accuracy(data)
    return render_template("stats.html", predictions=data.values(), accuracies=accuracies)

@app.route("/info")
def info():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("info.html")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)