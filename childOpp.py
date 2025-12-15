from simple_salesforce import Salesforce
from config import password, token

# Salesforce login
sf = Salesforce(
    username='nick.templeton@cognex.com',
    password=password(),
    security_token=token()
)

# ---- Parent Opportunity ID ----
PARENT_OPP_ID = "0064W00001JdubyQAB"

# ---- Field name for parent relationship ----
PARENT_FIELD = "Parent_Opportunity__c"   # update if needed


def get_child_opportunities(parent_id):
    soql = (
        "SELECT Id, Name, StageName, Amount, CloseDate "
        "FROM Opportunity "
        f"WHERE {PARENT_FIELD} = '{parent_id}' "
        "ORDER BY CreatedDate ASC"
    )

    result = sf.query_all(soql)
    records = result.get("records", [])

    if not records:
        print(f"No child opportunities found for parent {parent_id}.")
        return []

    print(f"\nChild Opportunities of {parent_id}:")
    print("----------------------------------------")

    for i, opp in enumerate(records, start=1):
        print(
            f"{i}. {opp['Name']} "
            f"(Id: {opp['Id']}, Stage: {opp.get('StageName')}, "
            f"Amount: {opp.get('Amount')}, CloseDate: {opp.get('CloseDate')})"
        )

    return records


# Run it
get_child_opportunities(PARENT_OPP_ID)
