from pydantic import BaseModel, ConfigDict

class TelegramBaseModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore"
    )