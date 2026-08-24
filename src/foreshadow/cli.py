import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def run(force: bool = False, date: str | None = None, llm: bool = False) -> None:
    raise NotImplementedError


@app.command()
def report(date: str | None = None, json: bool = False) -> None:
    raise NotImplementedError


@app.command()
def show(repo: str) -> None:
    raise NotImplementedError


@app.command()
def review(repo: str, action: str, m: str | None = None) -> None:
    raise NotImplementedError


@app.command()
def watchlist(action: str | None = None) -> None:
    raise NotImplementedError
