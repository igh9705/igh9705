from pydantic import BaseModel, Field, field_validator
from pathlib   import Path
from typing    import Optional, Literal
import yaml, decimal as D

class RuntimeCfg(BaseModel):
    loop_ms:   int
    cancel_tps:int
    log_level: str
    run_mode:  Literal["SIM", "LIVE"] = "LIVE"   # ★ 추가

class StratCfg(BaseModel):
    bp_threshold: float = Field(..., gt=0)     # %
    order_size_krw: int  = Field(..., gt=0)
    hedge_leverage: int  = Field(1, gt=0)   # 기본 1 배
    
    @property
    def band(self) -> D.Decimal:
        return D.Decimal(self.bp_threshold) / D.Decimal(100)

class ExchDef(BaseModel):
    id: str
    symbol: str
    ws_stream: Optional[str] = None          # spot엔 필요 없음

class FxCfg(BaseModel):
    source: str
    symbol: str
    poll_sec: int = 10

class Settings(BaseModel):
    runtime:  RuntimeCfg
    strategy: StratCfg
    exchanges: dict[str, ExchDef]
    fx: FxCfg                             # ★ 추가

def load_config(path: str | Path = "config.yaml") -> Settings:
    raw = yaml.safe_load(Path(path).read_text())
    return Settings(**raw)
