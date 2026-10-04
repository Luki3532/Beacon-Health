# How We Can and Can't Verify Credentials

Beacon Health System credentialing tool
**Last updated:** October 3, 2026

---

## The problem in one sentence

We need to check that about 100 radiology techs have current ARRT
certifications, and warn their managers before any of them expire.

---

## Why this is hard

The best case would be if ARRT had an **API** — a way for our program to ask
their website questions directly, without a person clicking through it. That
would let us check all 100 people in seconds.

ARRT doesn't offer one.

Their website also has a bot check (the "prove you're not a robot" step) on
the lookup page. That stops a program cold.

On top of that, ARRT's own rules say two things:

1. A file on their site called `robots.txt` tells automated programs to stay
   off the search page. That's the standard way a website says "no bots here."
2. Their Terms of Use say you can't copy or save their content in bulk without
   written permission.

**But here's the good news:** those same Terms say employers *are* allowed to
look up their own staff's certification and expiration dates. So what Beacon
wants to do is fine. It's the *automated bulk copying* that isn't.

Those are two different problems. The second one can be solved with a phone
call.

---

## What works (and is above board)

### Already built

| What it does | Where |
| --- | --- |
| Checks everyone against the federal exclusion list (76,331 names) | `v_6/screen.py` |
| Checks everyone against Michigan's sanctioned provider list (3,799 names) | `v_6/screen.py` |
| Tracks expiration dates and emails managers 30 days ahead | `v_1/run_alerts.py` |
| Builds a to-do list of who needs checking, and logs who checked them | `v_5/` |
| Prints a fill-in sheet for each person's ARRT lookup | `v_6/output/` |

Both of those databases hand out a full download file on purpose. We're using
them exactly the way they're meant to be used. Nothing is being scraped or
snuck around.

### Still worth trying

- **Call ARRT: 651.687.0048.** Ask what they offer employers who need to check
  a lot of people. This is the single best thing left to try. Hospitals do
  this all the time, so there's a decent chance something already exists.
- **Ask ARRT in writing** for permission. Their Terms describe how.
- **Hire a verification company** (ProviderTrust, Verifiable, Propelus). They
  already have permission. Costs money, but it's clean and the liability is
  theirs.
- **Just ask the techs.** Each person can pull up their own ARRT record and
  send it in. No permission needed. This is already how most of it gets done.
- **Add Indiana's list** if any staff work at Beacon's Indiana locations.
- **Add ARRT's discipline list** to catch someone losing their license in the
  middle of the year.

---

## What doesn't work (even though it might seem to)

| Idea | Why it's a bad idea |
| --- | --- |
| Use a robot browser to click through the site | Gets around the bot check they put there on purpose |
| Have an AI agent do the clicking instead | Exact same thing, just sounds better |
| Pay a service to solve the bot checks | Paying someone else to do it is still doing it |
| Rotate IP addresses so we're harder to spot | There's no innocent reason to do this |
| Fake the browser settings to look like a real person | Same |
| Go slow so it looks human | Pretending to be a person isn't being a person |
| Copy their discipline list anyway | "Public" doesn't mean "free to copy in bulk" |
| Log in as one of the techs | That's worse, not better |
| Buy the data from someone who scraped it | Still can't say where it came from |
| Build it and not tell Beacon | Hiding it is the worst part |

### Why none of these actually help

All of them get you a date. None of them get you a date you can **explain**.

If an inspector asks "where did this expiration date come from?" and the
answer is "our program got around their bot check," that's worse than having
no date at all. We'd be trading a slow process that holds up for a fast one
that falls apart.

There's also a practical risk. Websites block IP addresses that look like
bots. If ARRT blocks Beacon, Teresa loses the ability to look people up **by
hand** — which she can do today. That makes things worse, not better.

---

## Things people get wrong

### Sounds OK, isn't

- **"It's public, so we can take it."** Being able to see something doesn't
  mean you can copy all of it. ARRT says so directly.
- **"I signed an NDA."** That's an agreement with Beacon. ARRT never agreed to
  anything, so it doesn't give us permission.
- **"It's only 100 lookups, that's not scraping."** The amount isn't the
  issue. Going around the bot check is.
- **"We checked, so we're good for a year."** Not quite. Someone can lose
  their license mid-year and we'd never know. The discipline list would catch
  that.

### Sounds sketchy, is fine

- **Having our program read `robots.txt`.** That file exists *for* programs to
  read. Ours checks it every run, so we can prove we're following the rules
  instead of just saying we are.
- **Downloading the whole federal exclusion list.** They tell bulk users to do
  exactly this.
- **Keeping employee names next to exclusion records.** Fine to do, but keep
  the files local — don't put them anywhere shared.

### Still unclear

- Whether a manager doing one lookup counts as "personal use" under ARRT's
  rules. Probably yes, since they allow employer checks, but it's their call.
  Ask them.
- Whether we can share the Michigan data inside Beacon. Probably yes since
  it's a state public record, but nobody has confirmed it.

---

## Bottom line

Doing this the right way isn't the slow way. It's the way that produces proof
that holds up when someone asks — which is the whole point of credentialing.

What's standing in the way isn't a technical problem. It's a phone call nobody
has made yet.

**ARRT: 651.687.0048**
