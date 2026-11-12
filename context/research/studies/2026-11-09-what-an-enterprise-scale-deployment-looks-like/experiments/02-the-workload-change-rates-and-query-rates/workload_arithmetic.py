"""Convert the published figures into verb calls per user per day and per second at peak for a 1,000-user company.

Every input is a figure cited in ../../02-the-workload-change-rates-and-query-rates.md; every output is INFERRED from them.
Run: uv run python -I workload_arithmetic.py
"""

USERS = 1_000
FILES = 10_000_000
WORKDAY_HOURS = 8
WORKDAY_SECONDS = WORKDAY_HOURS * 3600


def rate(label, per_user_per_day, peak_factor):
    per_day = per_user_per_day * USERS
    mean_per_second = per_day / WORKDAY_SECONDS
    print(f"{label:70s} {per_user_per_day:>10.3f}/user/day {per_day:>12,.0f}/day {mean_per_second:>8.3f}/s mean {mean_per_second * peak_factor:>8.2f}/s peak (x{peak_factor})")


print("== Peak factors measured on real traces")
leung_corp_ops_per_day = 228e6 / 65
leung_eng_ops_per_day = 352e6 / 97
print(f"Leung corporate: mean ops/day {leung_corp_ops_per_day:,.0f}; peak day 9.4M = x{9.4e6 / leung_corp_ops_per_day:.2f}; peak hour 1.7M = x{1.7e6 / (leung_corp_ops_per_day / WORKDAY_HOURS):.2f} of the 8-hour-workday mean hour")
print(f"Leung engineering: mean ops/day {leung_eng_ops_per_day:,.0f}; peak day 19.1M = x{19.1e6 / leung_eng_ops_per_day:.2f}; peak hour 2.1M = x{2.1e6 / (leung_eng_ops_per_day / WORKDAY_HOURS):.2f} of the 8-hour-workday mean hour")
print(f"Google Piper: 800k peak / 500k workday mean = x{800 / 500:.1f}")
print(f"Leung corporate CIFS ops per client per day: {leung_corp_ops_per_day / 5261:,.0f}; engineering: {leung_eng_ops_per_day / 2654:,.0f}")
PEAK = 4.0  # the Leung hourly peak over the 8-hour mean, rounded; Google's 1.6 is the floor
print()

print("== Human search queries per user per working day")
stenmark_real_queries_per_day = 19_433 / 7
print(f"Stenmark 2002: {stenmark_real_queries_per_day:,.0f} real queries/day over ~60,000 employees = {stenmark_real_queries_per_day / 60_000:.3f}/employee/day; 5,644 unique IPs in the week = {5_644 / 60_000:.1%} of employees searched at all")
white_per_month = 200_000 / 50_000
print(f"Martin White 2018: 200,000/month over 50,000 unique users of 75,000 employees = {white_per_month:.1f}/active user/month = {white_per_month / 21:.2f}/active user/working day; {200_000 / 75_000 / 21:.3f}/employee/working day")
print(f"SparkToro 2024 web search: 121/searcher/month = {121 / 30:.1f}/day on every day (an upper bound for any search box)")
rate("Human ranked search (glean), intranet measurement, 0.05-0.2", 0.2, PEAK)
rate("Human ranked search (glean), web-search upper bound, 4/day", 4.0, PEAK)
rate("Clay's proposal: 100 queries/user/day", 100.0, PEAK)
print()

print("== Agent tool calls per user per working day")
actions_per_prompt = 10
turns_per_session = 4
print(f"Claude Code report: {actions_per_prompt} actions/prompt x {turns_per_session} turns/session = {actions_per_prompt * turns_per_session} actions/session")
for sessions_per_day in (2, 5, 10):
    rate(f"Agent: {sessions_per_day} Claude-Code-sized sessions/user/day x 40 actions", sessions_per_day * 40, PEAK)
print(f"SWE-agent: median 12 steps resolved, mean 21 unresolved, GPT-4 Turbo; SWE-smith on Verified: 25-29 steps (Claude 3.7 Sonnet)")
print()

print("== Files changed per day")
for label, share in (("Veeam 2% (bytes)", 0.02), ("Veeam 5% (bytes)", 0.05), ("Meyer 20%/month uniform upper bound", 0.20 / 21), ("Clay 1%", 0.01), ("Clay 10% nightly", 0.10)):
    print(f"{label:40s} {share:.4%} of {FILES:,} files = {share * FILES:,.0f} files/day = {share * FILES / USERS:,.1f} files/user/day")
print(f"Dropbox 2017: 1.2e9 files saved/day over 500M registered users = {1.2e9 / 500e6:.1f} files/user/day (registered, not active)")
print(f"Google 2015: 16,000 human commits/workday over 25,000 developers = {16_000 / 25_000:.2f} commits/dev/day; 40,000 total = {40_000 / 25_000:.1f}")
print(f"GitHub 2026: 34.3e9 commits/yr over 225M developers = {34.3e9 / 225e6 / 365:.2f} commits/dev/day (most registered developers are inactive)")
leung_writes_per_client_day = (177.7 + 364.4) / (65 + 97) 
print(f"Leung: writes are 1/3.2 (corp) and 1/2.3 (eng) of I/Os; 57-65% of files persist more than a day; over 90% of stored bytes untouched in three months")
