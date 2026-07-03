from data_loader.data_loader_api import load_survey_data
ds = load_survey_data("2026_Q2")

print(f"ds.insured_event_base rows: {len(ds.insured_event_base)}")
insured_yes = (ds.insured_event_base["q_child_wellbeing"] == "Yes").sum()
print(f"Yes in insured_event_base: {insured_yes}")