"""
STEP 1 of the Tally -> cloud sync.

Run this ON THE SAME PC/NETWORK AS TALLY (not on the cloud server).
It fetches the raw "Bills Receivable" report from Tally as XML and saves it
to a file so we can see the ACTUAL tag names your Tally install returns.

Tally's field names for this report can vary slightly by version/company
config, so rather than guess, this step just gets us real data to look at.

Requirements: none beyond the standard library.
Prereq in Tally: F1 -> Settings -> Advanced Configuration -> enable HTTP Server
(default port 9000).
"""

import urllib.request

TALLY_URL = "http://localhost:9000"   # change if Tally's HTTP server uses a different port
COMPANY_NAME = "YOUR COMPANY NAME HERE"  # must match exactly as it appears in Tally

XML_REQUEST = f"""<ENVELOPE>
 <HEADER>
  <TALLYREQUEST>Export</TALLYREQUEST>
 </HEADER>
 <BODY>
  <EXPORTDATA>
   <REQUESTDESC>
    <REPORTNAME>Bills Receivable</REPORTNAME>
    <STATICVARIABLES>
     <SVCURRENTCOMPANY>{COMPANY_NAME}</SVCURRENTCOMPANY>
     <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
    </STATICVARIABLES>
   </REQUESTDESC>
  </EXPORTDATA>
 </BODY>
</ENVELOPE>"""

def main():
    req = urllib.request.Request(
        TALLY_URL,
        data=XML_REQUEST.encode("utf-8"),
        headers={"Content-Type": "text/xml"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"Could not reach Tally at {TALLY_URL}: {e}")
        print("Check: Tally is running, HTTP Server is enabled (F1 > Settings > "
              "Advanced Configuration), and this script is running on the same "
              "PC/network as Tally.")
        return

    out_path = "tally_bills_receivable_raw.xml"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(raw)

    print(f"Saved response to {out_path} ({len(raw)} chars)")
    print("\n--- first 3000 characters ---\n")
    print(raw[:3000])
    print("\n---\n")
    print("Send me tally_bills_receivable_raw.xml (or paste the first 50-100 lines) "
          "so I can map the real party name / due date / pending amount tags "
          "into the sync agent.")

if __name__ == "__main__":
    main()
