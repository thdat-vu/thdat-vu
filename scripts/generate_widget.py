#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
CONFIG_PATH = os.path.join(REPO_ROOT, "widget_config.json")
OUTPUT_SVG = os.path.join(REPO_ROOT, "profile-widget.svg")

DARK_PALETTE = {
    "#ebedf0": "#161b22",
    "#9be9a8": "#0e4429",
    "#40c463": "#006d32",
    "#30a14e": "#26a641",
    "#216e39": "#39d353",
}

def get_github_token():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    # Try getting token from gh CLI if available
    try:
        res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return None

def fetch_github_data(username, token):
    query = """
    query($login: String!) {
      user(login: $login) {
        name
        followers { totalCount }
        repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC) {
          totalCount
          nodes {
            stargazerCount
          }
        }
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
                color
              }
            }
          }
        }
      }
    }
    """
    url = "https://api.github.com/graphql"
    req_body = json.dumps({"query": query, "variables": {"login": username}}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "GitAscii-Widget-Generator",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=req_body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "errors" in data:
                print("GraphQL errors:", data["errors"], file=sys.stderr)
            return data.get("data", {}).get("user")
    except Exception as e:
        print(f"Failed to fetch from GitHub API: {e}", file=sys.stderr)
        # Fallback to gh api if urllib fails
        try:
            cmd = ["gh", "api", "graphql", "-f", f"query={query}", "-F", f"login={username}"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                return data.get("data", {}).get("user")
        except Exception as e2:
            print(f"Fallback gh api also failed: {e2}", file=sys.stderr)
    return None

def calculate_stats(calendar):
    weeks = calendar.get("weeks", [])
    total_contributions = calendar.get("totalContributions", 0)
    all_days = [d for w in weeks for d in w.get("contributionDays", [])]

    if not all_days:
        return {
            "total_contributions": total_contributions,
            "start_date": "N/A",
            "end_date": "N/A",
            "current_streak": 0,
            "longest_streak": 0,
            "best_count": 0,
            "best_date": "N/A",
            "weeks": []
        }

    def fmt_date(ds):
        try:
            dt = datetime.strptime(ds, "%Y-%m-%d")
            return dt.strftime("%b %-d, %Y")
        except Exception:
            return ds

    start_date = fmt_date(all_days[0]["date"])
    end_date = fmt_date(all_days[-1]["date"])

    best_day = max(all_days, key=lambda d: d.get("contributionCount", 0))
    best_count = best_day.get("contributionCount", 0)
    best_date = fmt_date(best_day["date"])

    longest_streak = 0
    running_streak = 0
    for d in all_days:
        if d.get("contributionCount", 0) > 0:
            running_streak += 1
            if running_streak > longest_streak:
                longest_streak = running_streak
        else:
            running_streak = 0

    rev_days = list(reversed(all_days))
    start_idx = 0
    if rev_days and rev_days[0].get("contributionCount", 0) == 0:
        start_idx = 1

    current_streak = 0
    for d in rev_days[start_idx:]:
        if d.get("contributionCount", 0) > 0:
            current_streak += 1
        else:
            break

    return {
        "total_contributions": total_contributions,
        "start_date": start_date,
        "end_date": end_date,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "best_count": best_count,
        "best_date": best_date,
        "weeks": weeks
    }

def escape_xml(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

def generate_svg(config, gh_user):
    username = config.get("username", "thdat-vu")
    display_name = config.get("name", "Vu Thanh Dat")
    neofetch = config.get("neofetch", {})
    portrait_lines = config.get("portrait_lines", [])

    # Dynamic stats
    followers = 13
    public_repos = 25
    total_stars = 3
    cal_stats = None

    if gh_user:
        followers = gh_user.get("followers", {}).get("totalCount", followers)
        repos_data = gh_user.get("repositories", {})
        public_repos = repos_data.get("totalCount", public_repos)
        nodes = repos_data.get("nodes", [])
        if nodes:
            total_stars = sum(n.get("stargazerCount", 0) for n in nodes)
        cal_data = gh_user.get("contributionsCollection", {}).get("contributionCalendar", {})
        if cal_data:
            cal_stats = calculate_stats(cal_data)

    if not cal_stats:
        # Fallback dummy calendar
        cal_stats = {
            "total_contributions": 2783,
            "start_date": "Sep 14, 2025",
            "end_date": "Sep 19, 2026",
            "current_streak": 2,
            "longest_streak": 10,
            "best_count": 32,
            "best_date": "Sep 13, 2026",
            "weeks": []
        }

    # Widget 1: Portrait SVG lines
    portrait_rows_svg = []
    num_lines = min(len(portrait_lines), 75)
    for i in range(num_lines):
        line_text = portrait_lines[i]
        # In case line is already escaped, avoid double escaping
        if not re.search(r"&(?:amp|lt|gt|quot|apos);", line_text):
            line_text = escape_xml(line_text)

        y_text = 40.2 + i * 4.26
        y_clip = 37.0 + i * 4.26
        y_cursor = 38.0 + i * 4.26
        begin_time = i * 0.110
        end_time = begin_time + 0.110

        row_str = f"""<clipPath id="r-portrait-{i}"><rect x="20" y="{y_clip:.1f}" height="4.3" width="0"><animate attributeName="width" from="0" to="330.0" begin="{begin_time:.3f}s" dur="0.11s" fill="freeze"/></rect></clipPath>
<g clip-path="url(#r-portrait-{i})"><text xml:space="preserve" x="20" y="{y_text:.1f}" fill="#ffa657" font-size="3.7" textLength="330.0" lengthAdjust="spacing">{line_text}</text></g>
<rect y="{y_cursor:.1f}" width="4.0" height="2.3" fill="#ffa657" opacity="0"><animate attributeName="x" from="20" to="350.0" begin="{begin_time:.3f}s" dur="0.11s" fill="freeze"/><set attributeName="opacity" to="0.85" begin="{begin_time:.3f}s"/><set attributeName="opacity" to="0" begin="{end_time:.3f}s"/></rect>"""
        portrait_rows_svg.append(row_str)

    portrait_content = "\n".join(portrait_rows_svg)

    # Widget 2: Neofetch info lines
    now_text = escape_xml(neofetch.get("now", "“seven times down eight times up like the Daruma doll”\n― Chris Bradford, The Way of the Warrior"))
    now_font_size = "10.2" if len(now_text) > 48 else "12.5"
    also_text = escape_xml(neofetch.get("also", "Developer"))
    loc_text = escape_xml(neofetch.get("loc", "Ho Chi Minh City, Vietnam"))
    site_text = escape_xml(neofetch.get("site", "github.com"))
    stack = neofetch.get("stack", {})
    langs_text = escape_xml(stack.get("Langs", "Java, Python 3, Go, TypeScript"))
    fe_text = escape_xml(stack.get("Frontend", "Next.js"))
    be_text = escape_xml(stack.get("Backend", "Spring, FastAPI, Gin, PostgreSQL"))

    # Widget 3: Heatmap grid
    weeks = cal_stats.get("weeks", [])
    cells_svg = []
    month_labels_svg = []
    last_month = None
    last_month_col = -10

    MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    for col_idx, week in enumerate(weeks):
        days = week.get("contributionDays", [])
        col_x = 52.0 + col_idx * 11.93181818181818

        # Check month label
        for day in days:
            try:
                dt = datetime.strptime(day["date"], "%Y-%m-%d")
                if dt.month != last_month and (col_idx - last_month_col) >= 3:
                    last_month = dt.month
                    last_month_col = col_idx
                    month_name = MONTH_NAMES[dt.month]
                    month_labels_svg.append(
                        f'<text x="{col_x:.2f}" y="44" fill="#7d8590" font-size="10">{month_name}</text>'
                    )
                    break
            except Exception:
                pass

        for row_idx, day in enumerate(days):
            row_y = 50.0 + row_idx * 11.93181818181818
            delay = col_idx * 0.018 + row_idx * 0.045
            gh_color = day.get("color", "#ebedf0").lower()
            count = day.get("contributionCount", 0)

            # Map to dark palette
            if count == 0:
                cell_color = "#161b22"
            else:
                cell_color = DARK_PALETTE.get(gh_color)
                if not cell_color:
                    if count <= 5:
                        cell_color = "#0e4429"
                    elif count <= 14:
                        cell_color = "#006d32"
                    elif count <= 28:
                        cell_color = "#26a641"
                    else:
                        cell_color = "#39d353"

            date_str = day.get("date", "")
            tooltip = f"{date_str}: {count} contribution" + ("s" if count != 1 else "")
            cells_svg.append(
                f'<rect class="c-heatmap" style="animation-delay:{delay:.3f}s" x="{col_x:.2f}" y="{row_y:.2f}" width="9.545454545454545" height="9.545454545454545" rx="2.5" fill="{cell_color}"><title>{tooltip}</title></rect>'
            )

    heatmap_cells_str = "\n".join(cells_svg)
    month_labels_str = "\n".join(month_labels_svg)

    # Format numbers
    tot_contrib_str = f"{cal_stats['total_contributions']:,}"
    start_date_str = cal_stats['start_date']
    end_date_str = cal_stats['end_date']
    curr_streak = cal_stats['current_streak']
    long_streak = cal_stats['longest_streak']
    best_count = cal_stats['best_count']
    best_date = cal_stats['best_date']

    svg_template = f"""<svg width="800" height="624" viewBox="0 0 800 624" fill="none" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,100..800;1,100..800&amp;display=swap');

    * {{
      box-sizing: border-box;
    }}

    text {{
      user-select: none;
    }}

    .gitascii-canvas-bg {{
      fill: #0d1117;
      transition: fill 0.3s ease;
    }}

    @keyframes cell-anim {{
      0%   {{ opacity: 0; transform: translateY(-6px); }}
      100% {{ opacity: 1; transform: translateY(0); }}
    }}

    .c-heatmap {{
      opacity: 0;
      animation: cell-anim 0.42s cubic-bezier(.2,.8,.2,1) both;
    }}
  </style>

  <rect width="800" height="624" fill="#0d1117" rx="0" />

  <!-- Widget 1: Portrait terminal -->
  <g transform="translate(48, 40)" id="widget-portrait">
    <svg xmlns="http://www.w3.org/2000/svg" width="288" height="312" viewBox="0 0 370 400" preserveAspectRatio="xMidYMid meet" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">
      <defs>
        <linearGradient id="portrait-bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#0d1117"/>
          <stop offset="1" stop-color="#0d1117"/>
        </linearGradient>
      </defs>
      <rect width="370" height="400" rx="12" fill="url(#portrait-bg)"/>
      <rect x="0.5" y="0.5" width="369" height="399" rx="12" fill="none" stroke="#30363d" stroke-width="1"/>
      <line x1="0" y1="30" x2="370" y2="30" stroke="#30363d"/>
      <circle cx="20" cy="15" r="5" fill="#ff5f56"/>
      <circle cx="36" cy="15" r="5" fill="#ffbd2e"/>
      <circle cx="52" cy="15" r="5" fill="#27c93f"/>
      <text x="185" y="19" fill="#7d8590" font-size="12" text-anchor="middle">{username}@github: ~$ ./portrait.sh</text>
      
{portrait_content}

      <line x1="0" y1="357.0" x2="370" y2="357.0" stroke="#30363d"/>
      <text x="20" y="376.0" fill="#7d8590" font-size="13">{username}@github:~$ whoami <tspan fill="#ffa657">{display_name}</tspan></text>
      <rect x="247" y="364.0" width="8" height="14" fill="#ffa657">
        <animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.51;1" dur="1s" repeatCount="indefinite"/>
      </rect>
    </svg>
  </g>

  <!-- Widget 2: Neofetch terminal -->
  <g transform="translate(330, 42)" id="widget-neofetch">
    <svg xmlns="http://www.w3.org/2000/svg" width="456" height="312" viewBox="0 0 490 400" preserveAspectRatio="xMidYMid meet" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">
      <defs>
        <linearGradient id="infocard-bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#0d1117"/>
          <stop offset="1" stop-color="#0d1117"/>
        </linearGradient>
      </defs>
      <rect width="490" height="400" rx="12" fill="url(#infocard-bg)"/>
      <rect x="0.5" y="0.5" width="489" height="399" rx="12" fill="none" stroke="#30363d"/>
      <line x1="0" y1="30" x2="490" y2="30" stroke="#30363d"/>
      <circle cx="20" cy="15" r="5" fill="#ff5f56"/>
      <circle cx="36" cy="15" r="5" fill="#ffbd2e"/>
      <circle cx="52" cy="15" r="5" fill="#27c93f"/>
      <text x="245" y="19" fill="#7d8590" font-size="12" text-anchor="middle">{username}@github: ~$ neofetch</text>

      <g opacity="0" transform="translate(0,5)">
        <text x="20" y="60.0" font-size="14" font-weight="700">
          <tspan fill="#3fb950">{username}</tspan><tspan fill="#7d8590">@</tspan><tspan fill="#22d3ee">github</tspan>
        </text>
        <line x1="148" y1="56.0" x2="470" y2="56.0" stroke="#30363d" stroke-opacity="0.8"/>
        <animate attributeName="opacity" from="0" to="1" begin="0.15s" dur="0.4s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" begin="0.15s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </g>

      <g opacity="0" transform="translate(0,5)">
        <text x="20" y="84.0" fill="#ffa657" font-size="12.5" font-weight="700">Now</text>
        <text x="112" y="84.0" fill="#c9d1d9" font-size="{now_font_size}">{now_text}</text>
        <animate attributeName="opacity" from="0" to="1" begin="0.21s" dur="0.4s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" begin="0.21s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </g>

      <g opacity="0" transform="translate(0,5)">
        <text x="20" y="108.0" fill="#ffa657" font-size="12.5" font-weight="700">Also</text>
        <text x="112" y="108.0" fill="#c9d1d9" font-size="12.5">{also_text}</text>
        <animate attributeName="opacity" from="0" to="1" begin="0.27s" dur="0.4s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" begin="0.27s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </g>

      <g opacity="0" transform="translate(0,5)">
        <text x="20" y="132.0" fill="#ffa657" font-size="12.5" font-weight="700">Loc</text>
        <text x="112" y="132.0" fill="#c9d1d9" font-size="12.5">{loc_text}</text>
        <animate attributeName="opacity" from="0" to="1" begin="0.33s" dur="0.4s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" begin="0.33s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </g>

      <g opacity="0" transform="translate(0,5)">
        <text x="20" y="156.0" fill="#ffa657" font-size="12.5" font-weight="700">Site</text>
        <text x="112" y="156.0" fill="#c9d1d9" font-size="12.5">{site_text}</text>
        <animate attributeName="opacity" from="0" to="1" begin="0.39s" dur="0.4s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" begin="0.39s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </g>

      <g opacity="0" transform="translate(0,5)">
        <text x="20" y="192.0" fill="#58a6ff" font-size="12.5" font-weight="700">&#8212; Stack</text>
        <line x1="72" y1="188.0" x2="470" y2="188.0" stroke="#30363d" stroke-opacity="0.8"/>
        <animate attributeName="opacity" from="0" to="1" begin="0.51s" dur="0.4s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" begin="0.51s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </g>

      <g opacity="0" transform="translate(0,5)">
        <text x="20" y="216.0" fill="#ffa657" font-size="12.5" font-weight="700">Langs</text>
        <text x="112" y="216.0" fill="#c9d1d9" font-size="12.5">{langs_text}</text>
        <animate attributeName="opacity" from="0" to="1" begin="0.57s" dur="0.4s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" begin="0.57s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </g>

      <g opacity="0" transform="translate(0,5)">
        <text x="20" y="240.0" fill="#ffa657" font-size="12.5" font-weight="700">Frontend</text>
        <text x="112" y="240.0" fill="#c9d1d9" font-size="12.5">{fe_text}</text>
        <animate attributeName="opacity" from="0" to="1" begin="0.63s" dur="0.4s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" begin="0.63s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </g>

      <g opacity="0" transform="translate(0,5)">
        <text x="20" y="264.0" fill="#ffa657" font-size="12.5" font-weight="700">Backend</text>
        <text x="112" y="264.0" fill="#c9d1d9" font-size="12.5">{be_text}</text>
        <animate attributeName="opacity" from="0" to="1" begin="0.69s" dur="0.4s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" begin="0.69s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </g>

      <g opacity="0" transform="translate(0,5)">
        <text x="20" y="300.0" fill="#58a6ff" font-size="12.5" font-weight="700">&#8212; Highlights</text>
        <line x1="112" y1="296.0" x2="470" y2="296.0" stroke="#30363d" stroke-opacity="0.8"/>
        <animate attributeName="opacity" from="0" to="1" begin="0.81s" dur="0.4s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" begin="0.81s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </g>

      <g opacity="0" transform="translate(0,5)">
        <circle cx="23" cy="320.0" r="2.5" fill="#3fb950"/>
        <text x="34" y="324.0" fill="#c9d1d9" font-size="12.5">{public_repos} public repos, {followers} followers</text>
        <animate attributeName="opacity" from="0" to="1" begin="0.87s" dur="0.4s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" begin="0.87s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </g>

      <g opacity="0" transform="translate(0,5)">
        <circle cx="23" cy="344.0" r="2.5" fill="#3fb950"/>
        <text x="34" y="348.0" fill="#c9d1d9" font-size="12.5">Active developer with {total_stars} total stars</text>
        <animate attributeName="opacity" from="0" to="1" begin="0.93s" dur="0.4s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" begin="0.93s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </g>
    </svg>
  </g>

  <!-- Widget 3: Contributions Graph terminal -->
  <g transform="translate(48, 368)" id="widget-contributions">
    <svg xmlns="http://www.w3.org/2000/svg" width="704" height="240" viewBox="0 0 704 240" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">
      <defs>
        <linearGradient id="heatmap-bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#0d1420"/>
          <stop offset="1" stop-color="#0d1117"/>
        </linearGradient>
      </defs>
      <rect width="704" height="240" rx="12" fill="url(#heatmap-bg)"/>
      <rect x="0.5" y="0.5" width="703" height="239" rx="12" fill="none" stroke="#30363d" stroke-width="1" stroke-opacity="0.55"/>
      <line x1="0" y1="30" x2="704" y2="30" stroke="#30363d" stroke-opacity="0.35"/>
      <circle cx="22" cy="15" r="5" fill="#ff5f56"/>
      <circle cx="38" cy="15" r="5" fill="#ffbd2e"/>
      <circle cx="54" cy="15" r="5" fill="#27c93f"/>
      <text x="352" y="19" fill="#7d8590" font-size="12" text-anchor="middle">{username}@github: ~/contributions --graph</text>

{month_labels_str}

      <text x="22" y="69.4" fill="#7d8590" font-size="9">Mon</text>
      <text x="22" y="93.2" fill="#7d8590" font-size="9">Wed</text>
      <text x="22" y="117.1" fill="#7d8590" font-size="9">Fri</text>

{heatmap_cells_str}

      <text x="572.795" y="147.2" fill="#7d8590" font-size="10" text-anchor="end">Less</text>
      <rect x="578.795" y="139.52" width="9.545" height="9.545" rx="2.2" fill="#161b22"/>
      <rect x="590.727" y="139.52" width="9.545" height="9.545" rx="2.2" fill="#0e4429"/>
      <rect x="602.659" y="139.52" width="9.545" height="9.545" rx="2.2" fill="#006d32"/>
      <rect x="614.590" y="139.52" width="9.545" height="9.545" rx="2.2" fill="#26a641"/>
      <rect x="626.522" y="139.52" width="9.545" height="9.545" rx="2.2" fill="#39d353"/>
      <rect x="638.454" y="139.52" width="9.545" height="9.545" rx="2.2" fill="#69f0a0"/>
      <text x="682" y="147.2" fill="#7d8590" font-size="10" text-anchor="end">More</text>

      <line x1="0" y1="163.068" x2="704" y2="163.068" stroke="#30363d" stroke-opacity="0.25"/>
      <text x="22" y="187.068" font-size="13" fill="#39d353">
        <tspan font-weight="700">{tot_contrib_str}</tspan><tspan fill="#7d8590"> contributions in the last year</tspan>
      </text>
      <text x="682" y="187.068" font-size="12" fill="#7d8590" text-anchor="end">{start_date_str} &#8594; {end_date_str}</text>
      <text x="22" y="211.068" font-size="13" fill="#7d8590">
        current streak <tspan fill="#ffa657" font-weight="700">{curr_streak} days</tspan><tspan fill="#7d8590">   &#183;   longest </tspan><tspan fill="#ffa657" font-weight="700">{long_streak} days</tspan>
      </text>
      <text x="682" y="211.068" font-size="12" fill="#7d8590" text-anchor="end">best day <tspan fill="#f2cc60" font-weight="700">{best_count}</tspan> on {best_date}</text>
    </svg>
  </g>
</svg>
"""
    return svg_template

def main():
    print(f"Loading config from {CONFIG_PATH}...")
    if not os.path.exists(CONFIG_PATH):
        print(f"Error: Config file not found at {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    username = config.get("username", "thdat-vu")
    token = get_github_token()
    if token:
        print("GitHub token found.")
    else:
        print("Warning: No GitHub token found in env or gh CLI. API requests may be rate-limited.")

    print(f"Fetching GitHub data for {username}...")
    gh_user = fetch_github_data(username, token)
    if gh_user:
        print("GitHub data fetched successfully.")
    else:
        print("Warning: Could not fetch fresh GitHub data, using fallback values.")

    print("Generating SVG widget...")
    svg_content = generate_svg(config, gh_user)

    with open(OUTPUT_SVG, "w", encoding="utf-8") as f:
        f.write(svg_content)

    print(f"Profile widget successfully written to {OUTPUT_SVG}")

if __name__ == "__main__":
    main()
