import csv
import os

from openpyxl import Workbook


def export_events_csv(events, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["session_id", "person_name", "event_type", "ts", "confidence", "liveness_passed"])
        for row in events:
            writer.writerow(
                [
                    row.get("session_id"),
                    row.get("person_name"),
                    row.get("event_type"),
                    row.get("ts"),
                    row.get("confidence"),
                    row.get("liveness_passed"),
                ]
            )


def export_unknowns_csv(rows, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["session_id", "image_path", "ts"])
        for row in rows:
            writer.writerow(
                [
                    row.get("session_id"),
                    row.get("image_path"),
                    row.get("ts"),
                ]
            )


def export_alerts_csv(rows, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["session_id", "alert_type", "message", "ts"])
        for row in rows:
            writer.writerow(
                [
                    row.get("session_id"),
                    row.get("alert_type"),
                    row.get("message"),
                    row.get("ts"),
                ]
            )


def export_excel_from_csv(csv_path: str, xlsx_path: str):
    wb = Workbook()
    ws = wb.active

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            ws.append(row)

    wb.save(xlsx_path)


def export_html_report(events, unknowns, alerts, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    html = [
        "<html><head><meta charset='utf-8'><title>Live Attendance Report</title></head><body>",
        "<h1>Live Attendance Report</h1>",
        "<h2>Events</h2>",
        "<table border='1' cellspacing='0' cellpadding='6'>",
        "<tr><th>Session</th><th>Name</th><th>Type</th><th>Time</th><th>Confidence</th><th>Liveness</th></tr>",
    ]

    for row in events:
        html.append(
            f"<tr><td>{row.get('session_id')}</td><td>{row.get('person_name')}</td><td>{row.get('event_type')}</td>"
            f"<td>{row.get('ts')}</td><td>{row.get('confidence')}</td><td>{row.get('liveness_passed')}</td></tr>"
        )

    html.extend(["</table>", "<h2>Unknown Faces</h2>", "<table border='1' cellspacing='0' cellpadding='6'>"])
    html.append("<tr><th>Session</th><th>Image Path</th><th>Time</th></tr>")

    for row in unknowns:
        html.append(
            f"<tr><td>{row.get('session_id')}</td><td>{row.get('image_path')}</td><td>{row.get('ts')}</td></tr>"
        )

    html.extend(["</table>", "<h2>Alerts</h2>", "<table border='1' cellspacing='0' cellpadding='6'>"])
    html.append("<tr><th>Session</th><th>Type</th><th>Message</th><th>Time</th></tr>")

    for row in alerts:
        html.append(
            f"<tr><td>{row.get('session_id')}</td><td>{row.get('alert_type')}</td><td>{row.get('message')}</td><td>{row.get('ts')}</td></tr>"
        )

    html.extend(["</table>", "</body></html>"])

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html))