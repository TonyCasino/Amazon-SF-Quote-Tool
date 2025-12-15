from simple_salesforce import Salesforce
from config import password, token

# ---------------- Salesforce Login ----------------
sf = Salesforce(
    username='nick.templeton@cognex.com',
    password=password(),
    security_token=token()
)

# ---------------- CONFIG ----------------
QUOTE_ID = "a2MUe000002iWMPMA2"   # <-- Replace with the Quote Id you want to clear


def delete_all_quote_lines(quote_id):
    # Query all quote lines under this quote
    soql = (
        "SELECT Id FROM SBQQ__QuoteLine__c "
        f"WHERE SBQQ__Quote__c = '{quote_id}'"
    )

    result = sf.query_all(soql)
    quote_lines = result.get("records", [])

    print(f"Found {len(quote_lines)} quote line(s) to delete.")

    deleted_count = 0

    for line in quote_lines:
        line_id = line["Id"]
        try:
            sf.SBQQ__QuoteLine__c.delete(line_id)
            deleted_count += 1
            print(f"Deleted Quote Line: {line_id}")
        except Exception as e:
            print(f"Error deleting {line_id}: {e}")

    print(f"\nDone. Deleted {deleted_count} quote line(s).")


if __name__ == "__main__":
    delete_all_quote_lines(QUOTE_ID)
