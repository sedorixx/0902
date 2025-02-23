class GutachtenExtractor:
    def __init__(self):
        self.models = {}
        
    def extract_info(self, text: str) -> dict:
        return {}
        
    def get_model(self, info_type: str):
        return self.models.get(info_type)
        
    def save_model(self, info_type: str, model):
        self.models[info_type] = model