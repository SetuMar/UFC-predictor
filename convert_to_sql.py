# go through every file and convert/add it to a python dictionary
import json
import re
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup
from datetime import datetime
import sqlite3
import pandas as pd

# HELPER FUNCTIONS

def feet_inches_to_cm(text):
    '''
    Convert a height in feet and inches to centimetres
    
    Parameters:
    text (str): height in feet and inches, e.g. 5' 11"
    
    Returns:
    Height in centimetres, rounded to 1 decimal place.
    '''
    
    feet, inches = text.split("'")
    inches = inches.replace('"', "")
    total_inches = float(feet) * 12 + float(inches)
    return round(total_inches * 2.54, 1)


def inches_to_cm(text):
    '''
    Convert a measurement in inches (e.g. reach) to centimetres
    
    Parameters:
    text (str): measurement in inches, e.g. 72"
    
    Returns:
    Measurement in centimetres, rounded to 1 decimal place.
    '''
    
    inches = text.replace('"', "")
    return round(float(inches) * 2.54, 1)


def missing(text):
    '''
    Check if a value is missing
    
    Parameters:
    text (str): the scraped value
    
    Returns:
    True if the value is blank or a '--' placeholder, otherwise False.
    '''
    
    return text in ("", "--")


def to_float(text):
    '''
    Convert text to a float
    
    Parameters:
    text (str): the scraped value
    
    Returns:
    The value as a float, or None if missing.
    '''
    return None if missing(text) else float(text)


def pct(text):
    '''
    Convert a percentage to a decimal fraction
    
    Parameters:
    text (str): the percentage, e.g. 45
    
    Returns:
    The percentage as a decimal (e.g. 0.45), or None if missing.
    '''
    return None if missing(text) else float(text) / 100


def landed_attempted(text: str):
    '''
    Split a "landed of attempted" stat into two integers
    
    Parameters:
    text (str): the stat, e.g. 25 of 60
    
    Returns:
    A tuple of (landed, attempted), or (None, None) if missing.
    '''
    text = text.strip()
    if text in ("", "---", "--"):
        return None, None
    landed, attempted = text.split(" of ")
    return int(landed), int(attempted)


def time_to_seconds(text: str):
    '''
    Convert a mm:ss time (e.g. fight time or control time) to seconds
    
    Parameters:
    text (str): the time, e.g. 4:32
    
    Returns:
    Total seconds as an int, or None if missing.
    '''
    text = text.strip()
    if text in ("", "---", "--"):
        return None
    minutes, seconds = text.split(":")
    return int(minutes) * 60 + int(seconds)


def to_int(text: str):
    '''
    Convert text to an int
    
    Parameters:
    text (str): the scraped value
    
    Returns:
    The value as an int, or None if missing.
    '''
    text = text.strip()
    if text in ("", "---", "--"):
        return None
    return int(text)


def fight_duration_seconds(time_format: str, end_round: int, end_time_seconds: int):
    '''
    Calculate the total fight time using the round lengths in the time format
    
    Parameters:
    time_format (str): the fight's time format, e.g. 3 Rnd (5-5-5)
    end_round (int): the round the fight ended in
    end_time_seconds (int): seconds elapsed in the final round
    
    Returns:
    Total fight time in seconds, or None if the round lengths or end details are missing.
    '''
    round_lengths = re.findall(r"\d+", time_format.split("(")[-1]) if "(" in time_format else []
    if not round_lengths or end_round is None or end_time_seconds is None:
        return None
    completed_minutes = sum(int(length) for length in round_lengths[:end_round - 1])
    return completed_minutes * 60 + end_time_seconds


def column_values(td):
    '''
    Get both fighters' values from one stats table cell
    
    Parameters:
    td (Tag): the BeautifulSoup <td> cell, which holds one <p> per fighter
    
    Returns:
    A list of [first fighter's value, second fighter's value].
    '''
    return [p.get_text(strip=True) for p in td.select("p.b-fight-details__table-text")]

# ACTUAL FUNCTIONS

def get_event_info(event_path):
    '''
    Extract the main details of an event from its saved HTML page
    
    Parameters:
    event_path (str): path to the saved event HTML file
    
    Returns:
    A dict containing the event's id, title, date (YYYY-MM-DD) and a comma-separated string of its fight ids
    '''
    # load the saved html page
    file_path = Path(event_path)
    soup = BeautifulSoup(file_path.read_text(encoding="utf-8"), "html.parser")

    # the event id is the file name (without the extension)
    event_id = file_path.stem
    
    # get the event title
    title = soup.select_one(".b-content__title-highlight").get_text(strip=True)
    
    # get the event date and convert it to YYYY-MM-DD
    date_raw = soup.select_one("li.b-list__box-list-item").get_text(strip=True).removeprefix("Date:").strip()
    date_formatted = datetime.strptime(date_raw, "%B %d, %Y").strftime("%Y-%m-%d")

    # one row per fight on the card; the fight URL is in the row's data-link attribute
    fight_ids = ",".join(
        row["data-link"].removeprefix("http://ufcstats.com/fight-details/").strip("/")
        for row in soup.select("tbody.b-fight-details__table-body tr[data-link]")
    )

    return {
        "event_id": event_id,
        "title": title,
        "date": date_formatted,
        "fight_ids": fight_ids,
    }

def get_constant_fighter_info(fighter_path:str):
    '''
    Extract a fighter's profile info and career stats from their saved HTML page
    
    Parameters:
    fighter_path (str): path to the saved fighter HTML file
    
    Returns:
    A dict containing the fighter's id, name, physical attributes (height and reach in cm), stance, DOB and career averages
    '''
    # load the saved html page
    file_path = Path(fighter_path)
    html_content = file_path.read_text(encoding="utf-8")
        
    soup = BeautifulSoup(html_content, "html.parser")
    
    # get the fighter's name
    fighter_name = soup.select_one("span.b-content__title-highlight").get_text(strip=True)
    
    # get the fighter's physical attributes from the left info box (height, reach, stance, DOB)
    fighter_height = soup.select_one("div.b-list__info-box_style_small-width li.b-list__box-list-item").get_text(strip=True).removeprefix("Height:").strip()
    fighter_reach = soup.select_one("div.b-list__info-box_style_small-width li.b-list__box-list-item:nth-of-type(3)").get_text(strip=True).removeprefix("Reach:").strip()
    fighter_stance = soup.select_one("div.b-list__info-box_style_small-width li.b-list__box-list-item:nth-of-type(4)").get_text(strip=True).removeprefix('STANCE:').strip()
    fighter_DOB_raw = soup.select_one("div.b-list__info-box_style_small-width li.b-list__box-list-item:nth-of-type(5)").get_text(strip=True).removeprefix('DOB:').strip()
    
    # convert the DOB to YYYY-MM-DD (some fighters don't have one listed)
    fighter_DOB = None if missing(fighter_DOB_raw) else datetime.strptime(fighter_DOB_raw, "%b %d, %Y").strftime("%Y-%m-%d")
    
    # get the fighter's career striking stats from the middle info box (the % sign is removed from percentages)
    fighter_SLpM = soup.select_one("div.b-list__info-box_style_middle-width li.b-list__box-list-item:nth-of-type(1)").get_text(strip=True).removeprefix("SLpM:").strip()
    fighter_StrAcc = soup.select_one("div.b-list__info-box_style_middle-width li.b-list__box-list-item:nth-of-type(2)").get_text(strip=True).removeprefix("Str. Acc.:").strip().removesuffix("%")
    fighter_SApM = soup.select_one("div.b-list__info-box_style_middle-width li.b-list__box-list-item:nth-of-type(3)").get_text(strip=True).removeprefix("SApM:").strip()
    fighter_StrDef = soup.select_one("div.b-list__info-box_style_middle-width li.b-list__box-list-item:nth-of-type(4)").get_text(strip=True).removeprefix("Str. Def:").strip().removesuffix("%")
    
    # get the fighter's career grappling stats from the right info box
    fighter_tdAvg = soup.select_one("div.b-list__info-box-right li.b-list__box-list-item:nth-of-type(2)").get_text(strip=True).removeprefix("TD Avg.:").strip()
    fighter_tdAcc = soup.select_one("div.b-list__info-box-right li.b-list__box-list-item:nth-of-type(3)").get_text(strip=True).removeprefix("TD Acc.:").strip().removesuffix("%")
    fighter_tdDef = soup.select_one("div.b-list__info-box-right li.b-list__box-list-item:nth-of-type(4)").get_text(strip=True).removeprefix("TD Def.:").strip().removesuffix("%")
    fighter_SubAvg = soup.select_one("div.b-list__info-box-right li.b-list__box-list-item:nth-of-type(5)").get_text(strip=True).removeprefix("Sub. Avg.:").strip()

    # convert the scraped text into numbers and cm (missing values become None)
    return {
        'fighter_id': file_path.stem,
        'fighter_name': fighter_name,
        'fighter_height': None if missing(fighter_height) else feet_inches_to_cm(fighter_height),
        'fighter_reach': None if missing(fighter_reach) else inches_to_cm(fighter_reach),
        'fighter_stance': None if missing(fighter_stance) else fighter_stance,
        'fighter_DOB': fighter_DOB,

        'fighter_SLpM': to_float(fighter_SLpM),
        'fighter_StrAcc': pct(fighter_StrAcc),
        'fighter_SApM': to_float(fighter_SApM),
        'fighter_StrDef': pct(fighter_StrDef),
        'fighter_tdAvg': to_float(fighter_tdAvg),
        'fighter_tdAcc': pct(fighter_tdAcc),
        'fighter_tdDef': pct(fighter_tdDef),
        'fighter_SubAvg': to_float(fighter_SubAvg),
    }

def get_fight_info(fight_path: str):
    '''
    Extract all of the details and stats of a fight from its saved HTML page
    
    Parameters:
    fight_path (str): path to the saved fight HTML file
    
    Returns:
    A dict with 3 keys:
    fight: the bout info (event, fighters, winner, method, end round/time, etc.)
    fighter_stats: a list of 2 dicts containing each fighter's stat totals for the whole fight
    round_stats: a list of dicts containing each fighter's stats for every round
    '''
    # load the saved html page
    file_path = Path(fight_path)
    html_content = file_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html_content, "html.parser")
 
    # get the event name and id (the id is the last part of the event link)
    event_link = soup.select_one("h2.b-content__title a")
    event_name = event_link.get_text(strip=True)
    event_id = event_link["href"].rstrip("/").split("/")[-1]
 
    # each fighter has their own section containing their name, id and result (W/L/D/NC)
    persons = soup.select("div.b-fight-details__person")
    fighter_1_id = persons[0].select_one("a.b-fight-details__person-link")["href"].rstrip("/").split("/")[-1]
    fighter_1_name = persons[0].select_one("a.b-fight-details__person-link").get_text(strip=True)
    fighter_1_result = persons[0].select_one("i.b-fight-details__person-status").get_text(strip=True)
    fighter_2_id = persons[1].select_one("a.b-fight-details__person-link")["href"].rstrip("/").split("/")[-1]
    fighter_2_name = persons[1].select_one("a.b-fight-details__person-link").get_text(strip=True)
    fighter_2_result = persons[1].select_one("i.b-fight-details__person-status").get_text(strip=True)
 
    # get the winner's id
    if fighter_1_result == "W":
        winner_id = fighter_1_id
    elif fighter_2_result == "W":
        winner_id = fighter_2_id
    else:
        winner_id = None  # draw or no contest
 
    # ----- bout info -----
    # check if it was a title fight (the name contains "Title" or there is a belt icon)
    fight_title = soup.select_one("i.b-fight-details__fight-title").get_text(strip=True)
    title_icons = [img["src"] for img in soup.select("i.b-fight-details__fight-title img")]
    is_title_fight = "Title" in fight_title or any("belt.png" in src for src in title_icons)
    
    # get the weight class by removing the extra words from the fight title (ex. "UFC Lightweight Title Bout" -> "Lightweight")
    weight_class = fight_title.replace("UFC", "").replace("Title", "").replace("Bout", "").strip()
 
    # get how the fight ended
    method = soup.select_one("p.b-fight-details__text i.b-fight-details__text-item_first").get_text(strip=True).removeprefix("Method:").strip()
    
    # get the end round, end time, time format and referee
    text_items = soup.select("i.b-fight-details__text-item")
    end_round = text_items[0].get_text(strip=True).removeprefix("Round:").strip()
    end_time = text_items[1].get_text(strip=True).removeprefix("Time:").strip()
    time_format = text_items[2].get_text(strip=True).removeprefix("Time format:").strip()
    referee = text_items[3].get_text(strip=True).removeprefix("Referee:").strip()
    
    # get the extra method details (ex. the judges' scores or the finishing strike)
    details = soup.select("p.b-fight-details__text")[1].get_text(" ", strip=True).removeprefix("Details:").strip()
 
    # convert the end round and end time into numbers
    end_round = to_int(end_round)
    end_time_seconds = time_to_seconds(end_time)
 
    # store the bout info (empty details/referee become None)
    fight = {
        'fight_id': file_path.stem,
        'event_id': event_id,
        'event_name': event_name,
        'fighter_1_id': fighter_1_id,
        'fighter_1_name': fighter_1_name,
        'fighter_2_id': fighter_2_id,
        'fighter_2_name': fighter_2_name,
        'winner_id': winner_id,
        'fighter_1_result': fighter_1_result,
        'fighter_2_result': fighter_2_result,
        'weight_class': weight_class,
        'is_title_fight': is_title_fight,
        'method': method,
        'method_details': details or None,
        'end_round': end_round,
        'end_time_seconds': end_time_seconds,
        'time_format': time_format,
        'fight_duration_seconds': fight_duration_seconds(time_format, end_round, end_time_seconds),
        'referee': referee or None,
    }
 
    # some (mostly older) fights don't have stats tables, so return just the bout info
    tables = soup.select("table")
    if len(tables) < 4:
        return {'fight': fight, 'fighter_stats': [], 'round_stats': []}
 
    # index 0 refers to fighter 1 and index 1 refers to fighter 2 in every stats cell
    fighter_ids = [fighter_1_id, fighter_2_id]
    opponent_ids = [fighter_2_id, fighter_1_id]
 
    # tables[0] holds overall fighter totals and tables[2] holds the significant strikes breakdown
    # each column holds the values for both fighters (column 0 is the fighter names)
    totals_cols = [column_values(td) for td in tables[0].select("tbody tr td")]
    sig_cols = [column_values(td) for td in tables[2].select("tbody tr td")]
 
    # get each fighter's stats for the whole fight
    fighter_stats = []
    for i in range(2):
        # overall stats (knockdowns, strikes, takedowns, submissions, reversals, control time)
        kd = to_int(totals_cols[1][i])
        sig_landed, sig_attempted = landed_attempted(totals_cols[2][i])
        total_landed, total_attempted = landed_attempted(totals_cols[4][i])
        td_landed, td_attempted = landed_attempted(totals_cols[5][i])
        sub_att = to_int(totals_cols[7][i])
        reversals = to_int(totals_cols[8][i])
        ctrl_seconds = time_to_seconds(totals_cols[9][i])
 
        # significant strikes broken down by target (head, body, leg) and position (distance, clinch, ground)
        head_landed, head_attempted = landed_attempted(sig_cols[3][i])
        body_landed, body_attempted = landed_attempted(sig_cols[4][i])
        leg_landed, leg_attempted = landed_attempted(sig_cols[5][i])
        distance_landed, distance_attempted = landed_attempted(sig_cols[6][i])
        clinch_landed, clinch_attempted = landed_attempted(sig_cols[7][i])
        ground_landed, ground_attempted = landed_attempted(sig_cols[8][i])
 
        fighter_stats.append({
            'fight_id': file_path.stem,
            'fighter_id': fighter_ids[i],
            'opponent_id': opponent_ids[i],
            'kd': kd,
            'sig_str_landed': sig_landed,
            'sig_str_attempted': sig_attempted,
            'total_str_landed': total_landed,
            'total_str_attempted': total_attempted,
            'td_landed': td_landed,
            'td_attempted': td_attempted,
            'sub_att': sub_att,
            'reversals': reversals,
            'ctrl_seconds': ctrl_seconds,
            'head_landed': head_landed,
            'head_attempted': head_attempted,
            'body_landed': body_landed,
            'body_attempted': body_attempted,
            'leg_landed': leg_landed,
            'leg_attempted': leg_attempted,
            'distance_landed': distance_landed,
            'distance_attempted': distance_attempted,
            'clinch_landed': clinch_landed,
            'clinch_attempted': clinch_attempted,
            'ground_landed': ground_landed,
            'ground_attempted': ground_attempted,
        })
 
    # tables[1] holds the totals per round and tables[3] holds the significant strikes per round
    # only keep rows with <td> cells (this skips the round header rows)
    totals_round_rows = [tr for tr in tables[1].select("tr") if tr.select("td")]
    sig_round_rows = [tr for tr in tables[3].select("tr") if tr.select("td")]
 
    # get each fighter's stats for every round
    round_stats = []
    for round_number, (totals_row, sig_row) in enumerate(zip(totals_round_rows, sig_round_rows), start=1):
        totals_cols = [column_values(td) for td in totals_row.select("td")]
        sig_cols = [column_values(td) for td in sig_row.select("td")]
 
        for i in range(2):
            # split the "landed of attempted" stats (the single value stats are converted below)
            sig_landed, sig_attempted = landed_attempted(totals_cols[2][i])
            total_landed, total_attempted = landed_attempted(totals_cols[4][i])
            td_landed, td_attempted = landed_attempted(totals_cols[5][i])
            head_landed, head_attempted = landed_attempted(sig_cols[3][i])
            body_landed, body_attempted = landed_attempted(sig_cols[4][i])
            leg_landed, leg_attempted = landed_attempted(sig_cols[5][i])
            distance_landed, distance_attempted = landed_attempted(sig_cols[6][i])
            clinch_landed, clinch_attempted = landed_attempted(sig_cols[7][i])
            ground_landed, ground_attempted = landed_attempted(sig_cols[8][i])
 
            round_stats.append({
                'fight_id': file_path.stem,
                'fighter_id': fighter_ids[i],
                'opponent_id': opponent_ids[i],
                'round': round_number,
                'kd': to_int(totals_cols[1][i]),
                'sig_str_landed': sig_landed,
                'sig_str_attempted': sig_attempted,
                'total_str_landed': total_landed,
                'total_str_attempted': total_attempted,
                'td_landed': td_landed,
                'td_attempted': td_attempted,
                'sub_att': to_int(totals_cols[7][i]),
                'reversals': to_int(totals_cols[8][i]),
                'ctrl_seconds': time_to_seconds(totals_cols[9][i]),
                'head_landed': head_landed,
                'head_attempted': head_attempted,
                'body_landed': body_landed,
                'body_attempted': body_attempted,
                'leg_landed': leg_landed,
                'leg_attempted': leg_attempted,
                'distance_landed': distance_landed,
                'distance_attempted': distance_attempted,
                'clinch_landed': clinch_landed,
                'clinch_attempted': clinch_attempted,
                'ground_landed': ground_landed,
                'ground_attempted': ground_attempted,
            })
 
    return {'fight': fight, 'fighter_stats': fighter_stats, 'round_stats': round_stats}

def combine_fight_stats(fight: dict, fighter_stats: list, round_stats: list) -> dict:
    '''
    Combine a fight's bout info, stat totals and round stats into a single flat row
    
    Parameters:
    fight (dict): the bout info from get_fight_info
    fighter_stats (list): each fighter's stat totals for the fight
    round_stats (list): each fighter's stats for every round
    
    Returns:
    A dict containing the bout info plus every stat, named by fighter (and round) ex. fighter_1_kd, fighter_2_round_3_td_landed
    '''
    # start with a copy of the bout info
    combined = dict(fight)

    # keys that are already in the fight dict or are built into the new key names
    skip_keys = {'fight_id', 'fighter_id', 'opponent_id', 'round'}
    
    # match each fighter id to their side of the fight (1 or 2)
    sides = {fight['fighter_1_id']: '1', fight['fighter_2_id']: '2'}

    # ----- fight totals: fighter_1_kd, fighter_2_sig_str_landed, ... -----
    for stats in fighter_stats:
        side = sides[stats['fighter_id']]
        for key, value in stats.items():
            if key not in skip_keys:
                combined[f'fighter_{side}_{key}'] = value

    # ----- round stats: fighter_1_round_1_kd, fighter_2_round_3_td_landed, ... -----
    for stats in round_stats:
        side = sides[stats['fighter_id']]
        round_number = stats['round']
        for key, value in stats.items():
            if key not in skip_keys:
                combined[f'fighter_{side}_round_{round_number}_{key}'] = value

    return combined

def write_dict(path, dict):
    '''
    Save data to a JSON file
    
    Parameters:
    path (str): where to save the JSON file
    dict (dict or list): the data to save
    
    Returns:
    None
    '''
    # make sure the folder the file goes into exists
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # write the data as indented JSON (overwrites the file if it exists)
    with open(path, "w") as f:
        json.dump(dict, f, indent=4)
        
def load_json_dict(file_path: str ):
    '''
    Load previously saved data from a JSON file
    
    Parameters:
    file_path (str): path to the JSON file
    
    Returns:
    A tuple of (data, True) if the file loaded successfully, otherwise ([], False)
    '''
    path = Path(file_path)
    
    # the file doesn't exist or is empty, so there is nothing to load
    if not path.is_file() or path.stat().st_size == 0:
        return [], False

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
            return data, True
    
    # the file is incomplete or corrupted (ex. the script stopped while writing it)
    except (json.JSONDecodeError):
        return [], False

# load the saved event rows (if they have already been processed)
event_rows_path = "DICTDB/events.json"
event_rows, finished = load_json_dict(event_rows_path)

# otherwise, process every saved event page and save the results
if not finished:
    arr = list(Path("UFCDATA/event-details").iterdir())
    for i, p in enumerate(arr):
        event_rows.append(get_event_info(p))
        print(f'Loading Event Details: {i}/{len(arr)}')
        
    write_dict(event_rows_path, event_rows)
    
print("Events finished loading")

# paths for the processed fight data
fight_rows_path = "DICTDB/fightrows.json"
fight_stat_path = "DICTDB/fightstatrows.json"
round_stat_path = "DICTDB/roundstatrows.json"
combined_rows_path = "DICTDB/combinedrows.json"

# load all three fight tables (if they have already been processed)
fight_rows, f1_finished = load_json_dict(fight_rows_path)
fighter_stat_rows, f2_finished = load_json_dict(fight_stat_path)
round_stat_rows, f3_finished = load_json_dict(round_stat_path)

# if any file is missing, reset all three and reprocess every saved fight page (they are built together)
if not (f1_finished and f2_finished and f3_finished):
    fight_rows = []
    fighter_stat_rows = []
    round_stat_rows = []
    arr = list(Path("UFCDATA/fight-details").iterdir())
    for i, p in enumerate(arr):
        # split each fight's results into the three tables
        res = get_fight_info(p)
        fight_rows.append(res['fight'])
        fighter_stat_rows.extend(res['fighter_stats'])
        round_stat_rows.extend(res['round_stats'])
        print(f'Loading Fight Details: {i}/{len(arr)}')

    write_dict(fight_rows_path, fight_rows)
    write_dict(fight_stat_path, fighter_stat_rows)
    write_dict(round_stat_path, round_stat_rows)

print("Fights finished loading")

# load the combined rows (if they have already been processed)
combined_rows, finished = load_json_dict(combined_rows_path)

if not finished:
    # initialize an empty list to safely append to
    combined_rows = []

    # group the stat rows by fight so each fight can find its own stats
    fighter_stats_by_fight = defaultdict(list)
    for row in fighter_stat_rows:
        fighter_stats_by_fight[row['fight_id']].append(row)

    round_stats_by_fight = defaultdict(list)
    for row in round_stat_rows:
        round_stats_by_fight[row['fight_id']].append(row)

    # combine each fight with its stats into a single row
    for i, fight in enumerate(fight_rows):
        combined_rows.append(combine_fight_stats(
            fight,
            fighter_stats_by_fight[fight['fight_id']],
            round_stats_by_fight[fight['fight_id']],
        ))
        print(f'Combining Fight Stats: {i}/{len(fight_rows)}')

    write_dict(combined_rows_path, combined_rows)

print("Combined stats finished loading")

# load the saved fighter rows (if they have already been processed)
fighter_rows_path = "DICTDB/fighterdetails.json"
fighter_rows, finished = load_json_dict(fighter_rows_path)

# otherwise, process every saved fighter page and save the results
if not finished:
    # initialize an empty list to safely append to
    fighter_rows = []
    arr = list(Path("UFCDATA/fighter-details").iterdir())
    for i, p in enumerate(arr):
        fighter_rows.append(get_constant_fighter_info(p))
        print(f'Loading Fighter Details: {i}/{len(arr)}')
        
    write_dict(fighter_rows_path, fighter_rows)

print("Fighters finished loading")

# I probably could just read these as .json but might as well just store them as sql db might be useful in the future
conn = sqlite3.connect("ufc.db") 

# save each table to the database (replacing any old versions)
pd.DataFrame(event_rows).to_sql("events", conn, if_exists="replace", index=False)
pd.DataFrame(fighter_rows).to_sql("fighters", conn, if_exists="replace", index=False)
pd.DataFrame(fight_rows).to_sql("fights", conn, if_exists="replace", index=False)
pd.DataFrame(fighter_stat_rows).to_sql("fight_stats", conn, if_exists="replace", index=False)
pd.DataFrame(round_stat_rows).to_sql("round_stats", conn, if_exists="replace", index=False)
pd.DataFrame(combined_rows).to_sql("combined_fight_info", conn, if_exists="replace", index=False)

conn.close()