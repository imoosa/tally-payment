from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import pandas as pd
import json
import os
from datetime import datetime, date
import hashlib

app = Flask(__name__)
app.secret_key = 'maktronic_secret_2024_change_in_production'

# ── Auth ──────────────────────────────────────────────────────────────────────
USERS = {
    'admin': hashlib.sha256('admin123'.encode()).hexdigest(),
    'manager': hashlib.sha256('manager123'.encode()).hexdigest(),
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ── Data helpers ──────────────────────────────────────────────────────────────
DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'debtors.json')

BUCKETS = [
    {'key': 'lt30',    'label': '< 30 Days',     'col': 5,  'min': 0,   'max': 29},
    {'key': '30_60',   'label': '30 – 60 Days',  'col': 7,  'min': 30,  'max': 59},
    {'key': '60_90',   'label': '60 – 90 Days',  'col': 9,  'min': 60,  'max': 89},
    {'key': '90_120',  'label': '90 – 120 Days', 'col': 11, 'min': 90,  'max': 119},
    {'key': '120_180', 'label': '120 – 180 Days','col': 13, 'min': 120, 'max': 179},
    {'key': 'gt180',   'label': '> 180 Days',    'col': 15, 'min': 180, 'max': 9999},
]

def parse_excel(filepath):
    df = pd.read_excel(filepath, sheet_name='Sundry Debtors', header=None)
    parties = []
    for _, row in df.iloc[16:].iterrows():
        name_raw = str(row[0]) if pd.notna(row[0]) else ''
        if not name_raw or name_raw == 'nan':
            continue
        try:
            total = float(row[3]) if pd.notna(row[3]) else 0
        except:
            total = 0
        if total == 0:
            continue

        # split name and location
        parts = name_raw.rsplit(' - ', 1)
        name = parts[0].strip()
        location = parts[1].strip() if len(parts) == 2 else ''

        contact_person = str(row[1]).strip() if pd.notna(row[1]) else ''
        phone = str(row[2]).strip() if pd.notna(row[2]) else ''

        buckets = {}
        for b in BUCKETS:
            try:
                val = float(row[b['col']]) if pd.notna(row[b['col']]) else 0
            except:
                val = 0
            if val > 0:
                buckets[b['key']] = round(val, 2)

        if not buckets:
            continue

        parties.append({
            'name': name,
            'location': location,
            'contact_person': contact_person if contact_person != 'nan' else '',
            'phone': phone if phone != 'nan' else '',
            'total_pending': round(total, 2),
            'buckets': buckets,
            'last_updated': datetime.now().strftime('%Y-%m-%d'),
        })
    return parties

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return []

def save_data(parties):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump(parties, f, indent=2)

def get_summary(parties):
    totals = {b['key']: 0 for b in BUCKETS}
    counts = {b['key']: 0 for b in BUCKETS}
    grand_total = 0
    for p in parties:
        grand_total += p['total_pending']
        for bkey, bval in p['buckets'].items():
            totals[bkey] = round(totals.get(bkey, 0) + bval, 2)
            counts[bkey] = counts.get(bkey, 0) + 1
    return {'totals': totals, 'counts': counts, 'grand_total': round(grand_total, 2), 'total_parties': len(parties)}

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        u = request.form.get('username', '')
        p = hashlib.sha256(request.form.get('password', '').encode()).hexdigest()
        if USERS.get(u) == p:
            session['user'] = u
            return redirect(url_for('dashboard'))
        error = 'Invalid credentials'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    parties = load_data()
    summary = get_summary(parties)
    return render_template('dashboard.html', summary=summary, buckets=BUCKETS, user=session['user'])

@app.route('/bucket/<bucket_key>')
@login_required
def bucket_view(bucket_key):
    parties = load_data()
    label = next((b['label'] for b in BUCKETS if b['key'] == bucket_key), bucket_key)
    bucket_parties = []
    for p in parties:
        if bucket_key in p['buckets']:
            bucket_parties.append({**p, 'bucket_amount': p['buckets'][bucket_key]})
    bucket_parties.sort(key=lambda x: x['bucket_amount'], reverse=True)
    bucket_total = sum(p['bucket_amount'] for p in bucket_parties)
    return render_template('bucket.html', parties=bucket_parties, bucket_key=bucket_key,
                           bucket_label=label, bucket_total=bucket_total,
                           buckets=BUCKETS, user=session['user'])

@app.route('/party/<path:party_name>')
@login_required
def party_detail(party_name):
    parties = load_data()
    party = next((p for p in parties if p['name'] == party_name), None)
    if not party:
        return redirect(url_for('dashboard'))
    bucket_map = {b['key']: b['label'] for b in BUCKETS}
    return render_template('party_detail.html', party=party, bucket_map=bucket_map,
                           buckets=BUCKETS, user=session['user'])

@app.route('/api/summary')
@login_required
def api_summary():
    parties = load_data()
    return jsonify(get_summary(parties))

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_excel():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400
    tmp = '/tmp/upload.xlsx'
    f.save(tmp)
    try:
        parties = parse_excel(tmp)
        save_data(parties)
        summary = get_summary(parties)
        return jsonify({'success': True, 'message': f'Loaded {len(parties)} parties', 'summary': summary})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

"""@app.route('/api/google-sheet', methods=['POST'])
@login_required
def sync_google_sheet():
    
    data = request.get_json()
    sheet_url = data.get('url', '')
    if not sheet_url:
        return jsonify({'error': 'No URL provided'}), 400
    try:
        # Convert Google Sheets URL to CSV export
        if 'spreadsheets/d/' in sheet_url:
            sheet_id = sheet_url.split('spreadsheets/d/')[1].split('/')[0]
            csv_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx'
        else:
            return jsonify({'error': 'Invalid Google Sheets URL'}), 400

        import urllib.request
        tmp = '/tmp/gsheet.xlsx'
        urllib.request.urlretrieve(csv_url, tmp)
        parties = parse_excel(tmp)
        save_data(parties)
        summary = get_summary(parties)
        return jsonify({'success': True, 'message': f'Synced {len(parties)} parties from Google Sheets', 'summary': summary})
    except Exception as e:
        return jsonify({'error': str(e)}), 500"""

@app.route('/api/google-sheet', methods=['POST'])
@login_required
def sync_google_sheet():
    """Sync from Google Sheets export URL (CSV export link)"""
    data = request.get_json()
    sheet_url = data.get('url', '')
    if not sheet_url:
        return jsonify({'error': 'No URL provided'}), 400
    
    tmp = '/tmp/gsheet.xlsx'
    
    try:
        # Convert Google Sheets URL to CSV export
        if 'spreadsheets/d/' in sheet_url:
            sheet_id = sheet_url.split('spreadsheets/d/')[1].split('/')[0]
            # Use XLSX export (same as original)
            xlsx_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx'
        else:
            return jsonify({'error': 'Invalid Google Sheets URL'}), 400

        import urllib.request
        import urllib.error
        
        # Download with proper headers
        req = urllib.request.Request(
            xlsx_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                # Check if download was successful
                if response.status != 200:
                    return jsonify({'error': f'Download failed with status: {response.status}'}), 400
                
                content = response.read()
                
                # Check if we got actual content
                if len(content) < 1000:  # XLSX files should be larger
                    return jsonify({'error': 'Downloaded file is too small. Make sure the sheet is shared publicly.'}), 400
                
                # Save the file
                with open(tmp, 'wb') as f:
                    f.write(content)
                    
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return jsonify({'error': 'Sheet not found. Make sure the sheet is shared publicly.'}), 400
            elif e.code == 403:
                return jsonify({'error': 'Access denied. Make sure sheet is shared with "Anyone with the link can view".'}), 400
            else:
                return jsonify({'error': f'HTTP Error {e.code}: {e.reason}'}), 400
        except urllib.error.URLError as e:
            return jsonify({'error': f'Network error: {e.reason}'}), 400
        
        # Verify file exists before parsing
        if not os.path.exists(tmp):
            return jsonify({'error': 'Failed to save downloaded file'}), 500
        
        # Now parse the file
        try:
            parties = parse_excel(tmp)
        except Exception as e:
            return jsonify({'error': f'Failed to parse Excel file: {str(e)}'}), 400
        
        # Clean up temp file
        try:
            os.remove(tmp)
        except:
            pass
            
        save_data(parties)
        summary = get_summary(parties)
        return jsonify({'success': True, 'message': f'Synced {len(parties)} parties from Google Sheets', 'summary': summary})
        
    except Exception as e:
        # Clean up on error
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except:
            pass
        return jsonify({'error': str(e)}), 500

TALLY_SYNC_API_KEY = os.environ.get('TALLY_SYNC_API_KEY', 'change-this-key-before-deploying')

def compute_buckets_from_bills(bills):
    """
    bills: list of {'due_date': 'YYYY-MM-DD', 'pending_amt': float}
    Buckets by days overdue (today - due_date), same day-ranges as BUCKETS above.
    """
    today = date.today()
    buckets = {}
    total = 0
    for bill in bills:
        try:
            amt = float(bill.get('pending_amt', 0) or 0)
        except (TypeError, ValueError):
            amt = 0
        if amt <= 0:
            continue
        total += amt

        due = bill.get('due_date')
        overdue_days = 0
        if due:
            try:
                due_date = datetime.strptime(due, '%Y-%m-%d').date()
                overdue_days = max((today - due_date).days, 0)
            except ValueError:
                overdue_days = 0

        for b in BUCKETS:
            if b['min'] <= overdue_days <= b['max']:
                buckets[b['key']] = round(buckets.get(b['key'], 0) + amt, 2)
                break

    return buckets, round(total, 2)

@app.route('/api/tally-sync', methods=['POST'])
def tally_sync():
    """
    Machine-to-machine endpoint for the local Tally sync agent.
    Deliberately NOT behind @login_required -- the agent has no browser session.
    Auth is a shared secret header instead: X-Sync-Key.

    Expected JSON body:
    {
      "parties": [
        {
          "name": "ABC Traders",
          "location": "Mumbai",
          "contact_person": "Mr. Sharma",
          "phone": "9876543210",
          "bills": [
            {"due_date": "2026-04-15", "pending_amt": 15000.00},
            {"due_date": "2026-06-01", "pending_amt": 8000.00}
          ]
        }
      ]
    }
    """
    key = request.headers.get('X-Sync-Key', '')
    if not key or key != TALLY_SYNC_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    raw_parties = data.get('parties', [])
    if not raw_parties:
        return jsonify({'error': 'No parties in payload'}), 400

    parties = []
    for rp in raw_parties:
        name = (rp.get('name') or '').strip()
        if not name:
            continue
        buckets, total = compute_buckets_from_bills(rp.get('bills', []))
        if not buckets:
            continue
        parties.append({
            'name': name,
            'location': rp.get('location', '') or '',
            'contact_person': rp.get('contact_person', '') or '',
            'phone': rp.get('phone', '') or '',
            'total_pending': total,
            'buckets': buckets,
            'last_updated': datetime.now().strftime('%Y-%m-%d'),
        })

    save_data(parties)
    summary = get_summary(parties)
    return jsonify({'success': True, 'message': f'Synced {len(parties)} parties from Tally', 'summary': summary})

@app.route('/api/search')
@login_required
def search():
    q = request.args.get('q', '').lower()
    parties = load_data()
    results = [p for p in parties if q in p['name'].lower() or q in p.get('location','').lower() or q in p.get('contact_person','').lower()]
    return jsonify(results[:20])

@app.route('/api/send-reminder', methods=['POST'])
@login_required
def send_reminder():
    data = request.get_json()
    party_name = data.get('party_name')
    # In production: integrate email/WhatsApp API here
    return jsonify({'success': True, 'message': f'Reminder queued for {party_name}'})

if __name__ == '__main__':
    # Pre-load sample data from the uploaded Excel
    if not os.path.exists(DATA_FILE):
        # Try to find sample file in current directory
        sample_paths = [
            'SUNDRY_DEBTOTS_09-05-2026__2_.xlsx',  # Look in current folder
            os.path.join(os.path.dirname(__file__), 'sample.xlsx'),
        ]
        
        loaded = False
        for sample in sample_paths:
            if os.path.exists(sample):
                try:
                    parties = parse_excel(sample)
                    save_data(parties)
                    print(f'✅ Pre-loaded {len(parties)} parties from {sample}')
                    loaded = True
                    break
                except Exception as e:
                    print(f'Pre-load error from {sample}: {e}')
        
        if not loaded:
            print('⚠️ No sample data found. Upload an Excel file from the dashboard.')
    else:
        parties = load_data()
        print(f'📊 Loaded {len(parties)} existing parties from data/debtors.json')
    
    app.run(debug=True, port=5050)
