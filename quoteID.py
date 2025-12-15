from simple_salesforce import Salesforce
from config import password, token

sf = Salesforce(
    username='nick.templeton@cognex.com',
    password=password(),
    security_token=token()
)

QUOTE_NAME = "Q-439125"   # <-- ENTER QUOTE NAME HERE

def get_quote_id_by_name(quote_name: str):
    soql = (
        "SELECT Id, Name "
        "FROM SBQQ__Quote__c "
        f"WHERE Name = '{quote_name}' "
        "ORDER BY CreatedDate DESC "
        "LIMIT 1"
    )

    result = sf.query_all(soql)
    records = result.get("records", [])

    if not records:
        print(f"No quote found with Name = '{quote_name}'")
        return None

    quote_id = records[0]["Id"]
    print(quote_id)
    return quote_id


# Run it
get_quote_id_by_name(QUOTE_NAME)
