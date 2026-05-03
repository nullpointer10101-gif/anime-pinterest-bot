import os
import json
import time
import random
import csv
from datetime import datetime, timezone

import yaml

from src.dedup import init_db, is_seen, mark_seen
from src.scraper import scrape_pins
from src.media import download_image, download_video, cleanup
from src.poster import post_pin
from src.notify import send_telegram

CONFIG_PATH = "config.yaml"
QUEUE_PATH = os.path.join("data", "queue.json")
LOG_PATH = os.path.join("data", "run_log.csv")


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_queue() -> list:
    if os.path.exists(QUEUE_PATH):
        with open(QUEUE_PATH) as f:
            return json.load(f)
    return []


def save_queue(queue: list):
    os.makedirs("data", exist_ok=True)
    with open(QUEUE_PATH, "w") as f:
        json.dump(queue, f, indent=2)


def log_run(posted: int, skipped: int, errors: int):
    os.makedirs("data", exist_ok=True)
    write_header = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "posted", "skipped", "errors"])
        writer.writerow([datetime.now(timezone.utc).isoformat(), posted, skipped, errors])


def main():
    print("=" * 50)
    print(f"Pinterest Bot starting — {datetime.now(timezone.utc).isoformat()}")
    print("=" * 50)

    config = load_config()
    email = os.environ["PINTEREST_EMAIL"]
    password = os.environ["PINTEREST_PASSWORD"]

    posted = 0
    skipped = 0
    errors = 0

    # Initialize dedup database
    init_db()

    # Load existing queue, or scrape fresh pins to fill it
    queue = load_queue()

    if len(queue) < config["pins_per_run"]:
        print(f"[main] Queue has {len(queue)} pins, scraping more...")
        for source_url in config.get("source_urls", []):
            print(f"[main] Scraping {source_url}...")
            fresh_pins = scrape_pins(
                source_url=source_url,
                email=email,
                password=password,
                limit=config["scrape_limit"],
            )
            # Add only unseen pins to queue
            for pin in fresh_pins:
                if not is_seen(pin["pin_id"]):
                    if pin not in queue:
                        queue.append(pin)

        save_queue(queue)
        print(f"[main] Queue now has {len(queue)} pins")

    if not queue:
        msg = "Pinterest Bot: No new pins found to post."
        print(msg)
        send_telegram(msg)
        log_run(0, 0, 0)
        return

    # Post up to pins_per_run pins
    to_post = queue[:config["pins_per_run"]]
    remaining = queue[config["pins_per_run"]:]

    for pin in to_post:
        pin_id = pin["pin_id"]

        # Double-check dedup (in case DB was updated mid-run)
        if is_seen(pin_id):
            print(f"[main] Skipping already-seen pin {pin_id}")
            skipped += 1
            continue

        print(f"[main] Processing pin {pin_id} (type: {pin['pin_type']})")

        # Download media
        local_file = None
        for attempt in range(config["max_retries"]):
            try:
                if pin["pin_type"] == "video":
                    local_file = download_video(pin["media_url"], pin_id)
                else:
                    local_file = download_image(pin["media_url"], pin_id)
                if local_file:
                    break
            except Exception as e:
                print(f"[main] Download attempt {attempt + 1} failed: {e}")
                time.sleep(5)

        if not local_file:
            print(f"[main] Could not download pin {pin_id}, skipping")
            errors += 1
            continue

        # Post pin
        success = False
        for attempt in range(config["max_retries"]):
            try:
                success = post_pin(
                    email=email,
                    password=password,
                    board_name=config["target_board_name"],
                    local_file=local_file,
                    description=pin.get("description", ""),
                )
                if success:
                    break
            except Exception as e:
                print(f"[main] Post attempt {attempt + 1} failed: {e}")
                time.sleep(10)

        cleanup(local_file)

        if success:
            mark_seen(pin_id)
            posted += 1
            print(f"[main] Posted pin {pin_id} ({posted}/{config['pins_per_run']})")
        else:
            errors += 1
            print(f"[main] Failed to post pin {pin_id}")

        # Human-like delay between posts
        if posted < config["pins_per_run"]:
            delay = random.uniform(config["delay_min_seconds"], config["delay_max_seconds"])
            print(f"[main] Waiting {delay:.0f}s before next post...")
            time.sleep(delay)

    # Save remaining queue
    save_queue(remaining)

    # Log run
    log_run(posted, skipped, errors)

    # Send Telegram summary
    summary = (
        f"<b>Pinterest Bot Run Complete</b>\n"
        f"Posted: {posted}\n"
        f"Skipped (already seen): {skipped}\n"
        f"Errors: {errors}\n"
        f"Queue remaining: {len(remaining)}\n"
        f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    send_telegram(summary)

    print("=" * 50)
    print(f"Run complete — posted {posted}, skipped {skipped}, errors {errors}")
    print("=" * 50)


if __name__ == "__main__":
    main()
