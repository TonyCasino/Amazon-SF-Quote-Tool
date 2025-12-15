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

# Child opportunities (the ones you listed)
SOURCE_OPPORTUNITY_IDS = [
    "006Ue00000IQeYyIAL",  # Child of TEST for Nick 1
    "006Ue00000IQt4xIAD",  # Child of TEST for Nick 2 WOA
]

# The quote you want to copy all lines INTO
TARGET_QUOTE_ID = "a2MUe000003TLYnMAO"  # <-- replace with your target Quote Id

# Field on SBQQ__Quote__c that links to Opportunity
QUOTE_OPPORTUNITY_FIELD = "SBQQ__Opportunity2__c"

# Which fields from SBQQ__QuoteLine__c to copy
FIELDS_TO_COPY = [
    "SBQQ__Product__c",
    "SBQQ__Quantity__c",
    "SBQQ__ListPrice__c",
    "SBQQ__RegularPrice__c",
    "SBQQ__NetPrice__c",
    "SBQQ__Discount__c",
    "SBQQ__SubscriptionPricing__c",
    "SBQQ__Description__c",
    "SAP_Configuration__c",
    # Add your customs if needed:
    # "Station__c",
    # "View_Name__c",
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


def get_opportunity(opp_id: str):
    soql = (
        "SELECT Id, Name "
        "FROM Opportunity "
        f"WHERE Id = '{opp_id}' "
        "LIMIT 1"
    )
    result = sf.query_all(soql)
    recs = result.get("records", [])
    return recs[0] if recs else None


def get_quote_lines(quote_id: str):
    """
    Return all quote lines for a given Quote Id.
    """
    soql = (
        "SELECT Id, Name, "
        + ", ".join(FIELDS_TO_COPY) +
        " FROM SBQQ__QuoteLine__c "
        f"WHERE SBQQ__Quote__c = '{quote_id}'"
    )

    result = sf.query_all(soql)
    records = result.get("records", [])

    print(f"Found {len(records)} quote line(s) on Quote {quote_id}")
    return records


def create_quote_line_group(target_quote_id: str, group_name: str, description: str = None):
    """
    Create a SBQQ__QuoteLineGroup__c on the target quote.
    """
    data = {
        "SBQQ__Quote__c": target_quote_id,
        "Name": group_name,
    }
    if description:
        data["SBQQ__Description__c"] = description

    result = sf.SBQQ__QuoteLineGroup__c.create(data)
    group_id = result.get("id")
    print(f"✅ Created Quote Line Group '{group_name}' ({group_id}) on quote {target_quote_id}")
    return group_id


def copy_quote_lines_to_target(source_quote_line_records, target_quote_id: str, group_id: str):
    """
    Create new quote lines under target_quote_id,
    copying the fields listed in FIELDS_TO_COPY from each source line,
    assigning them to SBQQ__Group__c = group_id.
    """
    created_ids = []

    for line in source_quote_line_records:
        new_line_data = {
            "SBQQ__Quote__c": target_quote_id,
            "SBQQ__Group__c": group_id,  # <- this puts them into the group
        }

        for field in FIELDS_TO_COPY:
            if field not in line:
                continue

            value = line[field]
            if value is None:
                continue

            # Optional: SAP truncation safety
            if field == "SAP_Configuration__c" and isinstance(value, str):
                max_len = 130000
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

            created = sf.SBQQ__QuoteLine__c.get(new_id)
            print(
                f"✅ New Line {new_id}: Quote={created.get('SBQQ__Quote__c')}, "
                f"Group={created.get('SBQQ__Group__c')}, "
                f"Product={created.get('SBQQ__Product__c')}, "
                f"Qty={created.get('SBQQ__Quantity__c')}"
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

    # For each child Opportunity:
    for opp_id in SOURCE_OPPORTUNITY_IDS:
        print(f"\n=== Processing Opportunity {opp_id} ===")

        opp = get_opportunity(opp_id)
        opp_name = opp["Name"] if opp else opp_id

        # 1) Get a quote for this opp
        quote = get_quote_for_opportunity(opp_id)
        if not quote:
            continue

        # 2) Get the quote lines on that quote
        lines = get_quote_lines(quote["Id"])
        if not lines:
            print(f"No quote lines found for quote {quote['Id']} (opp {opp_id})")
            continue

        # 3) Create a quote line group on the target quote for this child opp
        group_name = f"{opp_name}"
        group_desc = f"Lines copied from quote {quote['Name']} ({quote['Id']})"
        group_id = create_quote_line_group(TARGET_QUOTE_ID, group_name, group_desc)

        # 4) Copy lines into that group
        created_ids = copy_quote_lines_to_target(lines, TARGET_QUOTE_ID, group_id)
        total_created += len(created_ids)

    print(f"\n🎉 Done. Created {total_created} new grouped quote line(s) on target quote {TARGET_QUOTE_ID}.")


if __name__ == "__main__":
    main()
