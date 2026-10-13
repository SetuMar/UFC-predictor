import json
import time

from playwright.sync_api import sync_playwright
import os
from pathlib import Path

# UFC url
UFC_URL = 'http://ufcstats.com/statistics/events/completed?page=all'

def write_array(array, file_path: str):
    """
    Save a list. Parent folders are created if they don't exist.

    Parameters:
    array: an array to write
    file_path (str): where to write
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # dump array into json file (if it exists)
    if path.suffix == ".json":
        path.write_text(json.dumps(array, indent=2, default=str), encoding="utf-8")
    else:
        # create file if it doesn't exist and write the file
        with path.open("w", encoding="utf-8") as f:
            for item in array:
                f.write(f"{item}\n")
    
    # message to user
    print(f"Wrote {len(array)} items to {path}")

def read_txt_array(file_path: str):
    """
    Read a plain-text file into a list.
    
    Parameters:
    file_path (str): location of path to read
    
    Returns:
    list of all information
    """
    # open file
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as f:
        # remove newline
        lines = [line.rstrip("\n") for line in f]
    # inform user
    print(f"Read {len(lines)} items from {path}")
    # return lines
    return lines

def download_url(page, wait_selector, url:str, save_path: str):
    '''
    Download a page's url
    
    Parameters:
    page: playwright page
    wait_selector: selector to wait for loading
    url (str): page to load
    save_path (str): where to save page
    '''
    # generate save path
    fp = Path(save_path)
    
    # if path exists, return
    if fp.exists():
        page.set_content(fp.read_text(encoding="utf-8"))
        return

    # if parent doesn't exist make directory
    fp.parent.mkdir(parents=True, exist_ok=True)
    
    # go to page and wait for the selector
    page.goto(url)
    page.wait_for_selector(wait_selector, timeout=60000)
    
    # get page html content
    html = page.content()
    
    # write content
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    # wait (be nice)
    time.sleep(2)

def get_url_data(page, default_page=UFC_URL, skip_first_two=False, *, selector):
    '''
    Get a page's url
    
    Parameters:
    page: playwright page
    default_page: where to start
    skip_first_two: skip first 2 links on page
    selector: url selector where to get url from
    
    Returns:
    links: list of links on a page
    '''
    # go to the page
    page.goto(default_page)

    # let the page load (max 1 minute) until the selector is found once
    page.wait_for_selector(selector, timeout=60000)

    # get every link's href attribute
    links = []
    for link_holder in page.locator(selector).all()[2 * skip_first_two:]:
        link = link_holder.get_attribute("href")
        links.append(link)
    
    # return links
    return links

with sync_playwright() as playwright:
    # chrome works best for me
    chromium = playwright.chromium
    # launch browser and a new page
    browser = chromium.launch(headless=True)
    # create new empty browser page
    page = browser.new_page()

    event_selector = "table.b-statistics__table-events i.b-statistics__table-content a"
    event_urls = read_txt_array('TMPDATA/event_urls.txt') if os.path.exists('TMPDATA/event_urls.txt') else []
    
    if not event_urls:
        # the first link is the one for an upcoming event
        event_urls = get_url_data(page, skip_first_two=True, selector=event_selector)
        write_array(event_urls, 'TMPDATA/event_urls.txt')
    
    print('event urls found')

    fight_selector = "tbody.b-fight-details__table-body td.b-fight-details__table-col:first-child a.b-flag"
    fight_urls = read_txt_array('TMPDATA/fight_urls.txt') if os.path.exists('TMPDATA/fight_urls.txt') else []
    
    if not fight_urls:
        for i, event_url in enumerate(event_urls):
            fight_urls = fight_urls + get_url_data(page, event_url, selector=fight_selector)
            download_url(page, fight_selector, event_url, f'UFCDATA/{event_url.removeprefix('http://ufcstats.com/')}.html')
            print(f'Downloading Event Pages: {i + 1}/{len(event_urls)}')
        write_array(fight_urls, 'TMPDATA/fight_urls.txt')
    
    print('fight urls found')

    fighter_selector = "a.b-fight-details__person-link"
    fighter_urls = read_txt_array('TMPDATA/fighter_urls.txt') if os.path.exists('TMPDATA/fighter_urls.txt') else []
    
    if not fighter_urls:
        for i, fight_url in enumerate(fight_urls):
            fighter_urls = fighter_urls + get_url_data(page, fight_url, selector=fighter_selector)
            download_url(page, fighter_selector, fight_url, f'UFCDATA/{fight_url.removeprefix('http://ufcstats.com/')}.html')
            print(f'Downloading Fight Pages: {i + 1}/{len(fight_urls)}')
        write_array(fighter_urls, 'TMPDATA/fighter_urls.txt')
    
    print('fighter urls found')

    for i, fighter_url in enumerate(fighter_urls):
        download_url(page, 'span.b-content__title-record', fighter_url, f'UFCDATA/{fighter_url.removeprefix('http://ufcstats.com/')}.html')
        print(f'Iterating through and downloading Fighter Pages: {i + 1}/{len(fighter_urls)}')
        
    print("Finished downloading all pages")

    # close browser
    browser.close()