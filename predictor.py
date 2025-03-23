import requests
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_file
import json
import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO

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
    "UEFA Nations League": 5,  # Liga Narodów UEFA
    "World Cup Qualifiers": 32 # Kwalifikacje MŚ (UEFA)
}

app = Flask(__name__)
app.secret_key = "super_tajny_klucz"  # Zmień na coś swojego
PASSWORD = "typertest123."  # Zmień na własne hasło
DATA_FILE = "predictions.json"

# Rejestracja czcionki dla PDF
pdfmetrics.registerFont(TTFont('DejaVuSans', 'fonts/DejaVuSans.ttf'))  # Ścieżka do czcionki

def get_team_id(team_name, league_id):
    headers = {"x-apisports-key": API_KEY}
    url = f"{BASE_URL}teams?league={league_id}&season=2024&name={team_name}"
    response = requests.get(url, headers=headers)
    data = response.json()
    return data["response"][0]["team"]["id"] if data["response"] else None

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
    if not team_id:
        return {"position": 20, "goals_for": 0, "goals_against": 0, "home_wins": 0, "away_wins": 0, "avg_goals_for": 0, "avg_goals_against": 0}
    
    headers = {"x-apisports-key": API_KEY}
    url = f"{BASE_URL}teams/statistics?league={league_id}&season=2024&team={team_id}"
    response = requests.get(url, headers=headers)
    data = response.json()
    
    if not data.get("response") or isinstance(data["response"], list):
        return {"position": 20, "goals_for": 0, "goals_against": 0, "home_wins": 0, "away_wins": 0, "avg_goals_for": 0, "avg_goals_against": 0}
    
    data = data["response"]
    is_international = league_id in [5, 32]
    
    home_wins = data.get("fixtures", {}).get("wins", {}).get("home", 0) or 0
    away_wins = data.get("fixtures", {}).get("wins", {}).get("away", 0) or 0
    goals_for = data.get("goals", {}).get("for", {}).get("total", {"total": 0})
    goals_against = data.get("goals", {}).get("against", {}).get("total", {"total": 0})
    games_played = data.get("fixtures", {}).get("played", {}).get("total", 1) or 1
    
    if isinstance(home_wins, dict):
        home_wins = home_wins.get("total", 0)
        away_wins = away_wins.get("total", 0)
        goals_for = goals_for.get("total", 0)
        goals_against = goals_against.get("total", 0)
    else:
        goals_for = (goals_for.get("home", 0) + goals_for.get("away", 0)) if goals_for else 0
        goals_against = (goals_against.get("home", 0) + goals_against.get("away", 0)) if goals_against else 0

    return {
        "position": 1 if is_international else (int(data.get("rank", 20)) if data.get("rank") else 20),
        "goals_for": goals_for,
        "goals_against": goals_against,
        "home_wins": home_wins,
        "away_wins": away_wins,
        "avg_goals_for": goals_for / games_played,
        "avg_goals_against": goals_against / games_played
    }

def calculate_weighted_form(matches, league_id):
    points = 0
    weights = [1.5, 1.25, 1.0, 1.0, 1.0]
    for i, match in enumerate(matches[:5]):
        home_goals = match["goals"]["home"]
        away_goals = match["goals"]["away"]
        if home_goals is None or away_goals is None:
            continue
        
        home_team = match["teams"]["home"]["name"]
        away_team = match["teams"]["away"]["name"]
        opponent_id = match["teams"]["away"]["id"] if match["teams"]["home"]["winner"] else match["teams"]["home"]["id"]
        opponent_name = away_team if opponent_id == match["teams"]["away"]["id"] else home_team
        
        opponent_stats = get_team_stats(opponent_name, league_id)
        opponent_strength = 20 - opponent_stats["position"] + 1
        weight = weights[i] * (opponent_strength / 20)
        
        if home_goals > away_goals:
            points += 3 * weight if match["teams"]["home"]["winner"] else 0
        elif home_goals < away_goals:
            points += 3 * weight if match["teams"]["away"]["winner"] else 0
        else:
            points += 1 * weight
    return points

def calculate_streak(matches):
    streak = 0
    for match in matches[:3]:
        home_goals = match["goals"]["home"]
        away_goals = match["goals"]["away"]
        if home_goals is None or away_goals is None:
            break
        if home_goals > away_goals and match["teams"]["home"]["winner"]:
            streak += 1
        elif home_goals < away_goals and match["teams"]["away"]["winner"]:
            streak += 1
        else:
            break
    if streak >= 3:
        return 5
    streak = 0
    for match in matches[:2]:
        home_goals = match["goals"]["home"]
        away_goals = match["goals"]["away"]
        if home_goals is None or away_goals is None:
            break
        if home_goals < away_goals and not match["teams"]["home"]["winner"]:
            streak -= 1
        elif home_goals > away_goals and not match["teams"]["away"]["winner"]:
            streak -= 1
        else:
            break
    if streak <= -2:
        return -3
    return 0

def calculate_goal_trend(goals_for, goals_against, games_played):
    avg_goals_for = goals_for / games_played
    avg_goals_against = goals_against / games_played
    return min(avg_goals_for * 5, 10) - min(avg_goals_against * 3, 6)

def calculate_h2h(h2h_matches, team_name, is_home=False):
    points = 0
    for match in h2h_matches:
        home_team = match["teams"]["home"]["name"]
        home_goals = match["goals"]["home"]
        away_goals = match["goals"]["away"]
        if home_goals is None or away_goals is None:
            continue
        if is_home and home_team == team_name:
            points += 3 if home_goals > away_goals else 1 if home_goals == away_goals else 0
        elif not is_home and home_team != team_name:
            points += 3 if away_goals > home_goals else 1 if home_goals == away_goals else 0
    return points

def calculate_position_points(position):
    return max(20 - position + 1, 1)

def calculate_home_away_points(stats, is_home_team):
    return min(stats["home_wins"] * 2, 10) if is_home_team else min(stats["away_wins"] * 2, 10)

def predict_winner(team1, team2, league_name, match_date):
    league_id = LEAGUE_IDS[league_name]
    matches1 = get_last_5_matches(team1, league_id)
    matches2 = get_last_5_matches(team2, league_id)
    if not matches1 or not matches2:
        return None
    
    form1 = calculate_weighted_form(matches1, league_id)
    form2 = calculate_weighted_form(matches2, league_id)
    streak1 = calculate_streak(matches1)
    streak2 = calculate_streak(matches2)
    
    h2h_matches = get_h2h_matches(team1, team2, league_id)
    h2h1 = calculate_h2h(h2h_matches, team1, is_home=True)
    h2h2 = calculate_h2h(h2h_matches, team2, is_home=False)
    
    stats1 = get_team_stats(team1, league_id)
    stats2 = get_team_stats(team2, league_id)
    pos1 = calculate_position_points(stats1["position"])
    pos2 = calculate_position_points(stats2["position"])
    goal_trend1 = calculate_goal_trend(stats1["goals_for"], stats1["goals_against"], stats1.get("games_played", 1))
    goal_trend2 = calculate_goal_trend(stats2["goals_for"], stats2["goals_against"], stats2.get("games_played", 1))
    home_away1 = calculate_home_away_points(stats1, True)
    home_away2 = calculate_home_away_points(stats2, False)
    
    total1 = form1 + streak1 + h2h1 + pos1 + goal_trend1 + home_away1
    total2 = form2 + streak2 + h2h2 + pos2 + goal_trend2 + home_away2
    
    diff = abs(total1 - total2)
    if diff < 5:
        prediction = {team1: 40, "Draw": 35, team2: 25}
    elif total1 > total2:
        prediction = {team1: 60 + diff//2, "Draw": 20, team2: 20 - diff//2}
    else:
        prediction = {team1: 20 - diff//2, "Draw": 20, team2: 60 + diff//2}
    
    return {
        "match": f"{team1} vs {team2}",
        "prediction": prediction,
        "match_date": match_date,
        "league": league_name
    }

def get_upcoming_matches(league_name):
    league_id = LEAGUE_IDS[league_name]
    start_date = datetime.now().strftime("%Y-%m-%d")
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
            max_pred = max(pred["prediction"], key=pred["prediction"].get)
            if max_pred == pred["result"]:
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
    current_date = datetime.now().strftime("%Y-%m-%d")
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
    
    return render_template("index.html", predictions_by_league=predictions_by_league, accuracies=accuracies, current_date=current_date)

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

@app.route("/report")
def generate_report():
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
                    predictions_by_league[league].append(prediction)
        else:
            predictions_by_league[league] = None
    
    data = update_results()
    accuracies = calculate_accuracy(data)
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    styles['Normal'].fontName = 'DejaVuSans'
    styles['Heading1'].fontName = 'DejaVuSans'
    styles['Heading2'].fontName = 'DejaVuSans'
    styles['Heading3'].fontName = 'DejaVuSans'
    elements = []
    
    elements.append(Paragraph("Typer Piłkarski - Raport", styles['Heading1']))
    elements.append(Spacer(1, 12))
    
    elements.append(Paragraph(f"Data: {datetime.now().strftime('%Y-%m-%d')}", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    elements.append(Paragraph("Typy na dziś", styles['Heading2']))
    for league, predictions in predictions_by_league.items():
        elements.append(Paragraph(league, styles['Heading3']))
        if predictions:
            for pred in predictions:
                max_pred = max(pred["prediction"], key=pred["prediction"].get)
                pred_str = f"{pred['match']} - {max_pred} ({pred['prediction'][max_pred]}%)"
                elements.append(Paragraph(pred_str, styles['Normal']))
        else:
            elements.append(Paragraph("Brak meczów", styles['Normal']))
        elements.append(Spacer(1, 6))
    
    elements.append(Paragraph("Skuteczność rozgrywek", styles['Heading2']))
    accuracy_data = [[league, f"{stats['correct']}/{stats['total']} ({stats['percent']:.2f}%)"] for league, stats in accuracies.items()]
    elements.append(Table([["Liga", "Skuteczność"]] + accuracy_data))
    
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="raport_typer.pdf", mimetype="application/pdf")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)