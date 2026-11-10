# gridlab

A small 4x4 grid world modelling the Spot "close down the lab" experiment, so a DIARC
planner can be evaluated on harder variants without running the real robot.

Status: step 2 of 6 (core model + lab objects). See `tests/test_lab.py` for a full solve of the default lab.

```bash
pip install -e .[dev]
python -m pytest -q
```
