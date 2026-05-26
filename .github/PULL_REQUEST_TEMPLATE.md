## Summary

-

## Verification

- [ ] `python3 -m compileall -q src tests`
- [ ] `python3 -m unittest -v`
- [ ] Setup/doctor smoke, when setup behavior changes

## Risk

-

## Notes

- Edgebase must stay local-first: no required cloud service, API key, Docker, or graph database.
- Existing agent config must be merged carefully and never blindly overwritten.
