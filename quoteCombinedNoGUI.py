from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceMalformedRequest
from config import password, token

# ---------------- Salesforce Login ----------------
sf = Salesforce(
    username='nick.templeton@cognex.com',
    password=password(),
    security_token=token()
)

# ---------------- CONFIG ----------------

# For each child Opportunity:
# - opp_id: the child Opportunity Id
# - copies: how many "instances" of that quote you want
#   (we'll multiply quantities by this instead of duplicating lines)
SOURCE_CONFIG = [
    {"opp_id": "006Ue00000IQeYyIAL", "copies": 2},  # 2x quantities from this quote
    {"opp_id": "006Ue00000IQt4xIAD", "copies": 1},  # 1x quantities from this quote
]

# The quote you want to copy all lines INTO
TARGET_QUOTE_ID = "a2MUe000003TLYnMAO"  # <-- replace with your target Quote Id

# Field on SBQQ__Quote__c that links to Opportunity
QUOTE_OPPORTUNITY_FIELD = "SBQQ__Opportunity2__c"

# Fields to copy from SBQQ__QuoteLine__c
# We'll handle SBQQ__Quantity__c specially (multiply it), so we won't copy it blindly.
FIELDS_TO_COPY = [
    "SBQQ__Product__c",
    # "SBQQ__Quantity__c",  # handled separately
    "SBQQ__ListPrice__c",
    "SBQQ__RegularPrice__c",
    "SBQQ__NetPrice__c",
    "SBQQ__Discount__c",
    "SBQQ__SubscriptionPricing__c",
    "SBQQ__Description__c",
    "SAP_Configuration__c",
    # add your customs here if needed: "Station__c", "View_Name__c", ...
]


# ---------------- Helper Functions ----------------

def get_quote_for_opportunity(opp_id: str):
    """
    Return a quote for the given Opportunity:
    - Prefer Primary (SBQQ__Primary__c = TRUE)
    - Otherwise, most recently created quote.
    """
    soql = (
        "SELECT Id, Name, SBQQ__Primary__c, CreatedDate "
        "FROM SBQQ__Quote__c "
        f"WHERE {QUOTE_OPPORTUNITY_FIELD} = '{opp_id}' "
        "ORDER BY SBQQ__Primary__c DESC, CreatedDate DESC"
    )
    result = sf.query_all(soql)
    records = result.get("records", [])

    if not records:
        print(f"No quotes found for Opportunity {opp_id}")
        return None

    quote = records[0]
    print(
        f"Using Quote {quote['Name']} (Id: {quote['Id']}, "
        f"Primary: {quote.get('SBQQ__Primary__c')}) for Opportunity {opp_id}"
    )
    return quote


def get_quote_lines(quote_id: str):
    """
    Return all quote lines for a given Quote Id.
    """
    soql = (
        "SELECT Id, Name, SBQQ__Quantity__c, "
        + ", ".join(FIELDS_TO_COPY) +
        " FROM SBQQ__QuoteLine__c "
        f"WHERE SBQQ__Quote__c = '{quote_id}'"
    )

    result = sf.query_all(soql)
    records = result.get("records", [])

    print(f"Found {len(records)} quote line(s) on Quote {quote_id}")
    return records


def copy_quote_lines_to_target(source_quote_line_records, target_quote_id: str, copies: int):
    """
    For each source line:
    - Create ONE new quote line on the target quote
    - Set Quantity = source_quantity * copies
    """
    created_ids = []

    for line in source_quote_line_records:
        new_line_data = {
            "SBQQ__Quote__c": target_quote_id,
        }

        # Handle quantity separately: multiply by 'copies'
        src_qty = line.get("SBQQ__Quantity__c")
        if src_qty is None:
            # If somehow null, assume 1 as base quantity
            src_qty = 1
            print(f"⚠️  Source line {line['Id']} has null quantity, assuming 1.")
        try:
            new_qty = float(src_qty) * copies
        except Exception:
            print(f"⚠️  Could not parse quantity on line {line['Id']}, defaulting to copies ({copies}).")
            new_qty = copies

        new_line_data["SBQQ__Quantity__c"] = new_qty

        # Copy all other fields
        for field in FIELDS_TO_COPY:
            if field not in line:
                continue

            value = line[field]
            if value is None:
                continue

            # Safety for huge SAP JSON blobs
            if field == "SAP_Configuration__c" and isinstance(value, str):
                max_len = 130000  # adjust if you know exact field length
                if len(value) > max_len:
                    print(
                        f"⚠️  SAP_Configuration__c too long on source {line['Id']} "
                        f"({len(value)} chars). Truncating to {max_len}."
                    )
                    value = value[:max_len]

            new_line_data[field] = value

        try:
            result = sf.SBQQ__QuoteLine__c.create(new_line_data)
            new_id = result.get("id")
            created_ids.append(new_id)
            print(
                f"✅ Created new Quote Line {new_id} on target quote "
                f"(from source {line['Id']}, qty {src_qty} * {copies} = {new_qty})"
            )
        except SalesforceMalformedRequest as e:
            print(f"\n❌ SalesforceMalformedRequest for source line {line['Id']}:")
            print("Payload we sent:")
            print(new_line_data)
            print("Error content from Salesforce:")
            print(e.content)
        except Exception as e:
            print(f"\n❌ Generic error creating quote line from source {line['Id']}: {e}")

    return created_ids


# ---------------- Main Logic ----------------

def main():
    total_created = 0

    for cfg in SOURCE_CONFIG:
        opp_id = cfg["opp_id"]
        copies = cfg["copies"]

        print(f"\n--- Processing Opportunity {opp_id} (quantity multiplier = {copies}) ---")
        quote = get_quote_for_opportunity(opp_id)
        if not quote:
            continue

        lines = get_quote_lines(quote["Id"])
        if not lines:
            print(f"No quote lines found for quote {quote['Id']} (opp {opp_id})")
            continue

        created_ids = copy_quote_lines_to_target(lines, TARGET_QUOTE_ID, copies)
        total_created += len(created_ids)

    print(f"\nDone. Created {total_created} new quote line(s) on target quote {TARGET_QUOTE_ID}.")


if __name__ == "__main__":
    main()
