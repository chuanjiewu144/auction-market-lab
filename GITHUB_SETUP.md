# Put Auction Market Lab on GitHub

## Upload the project folder

1. Download and extract `auction_market_lab.zip`. Enter the extracted `auction_market_lab` folder: this is the repository root, containing `README.md`, `auction_lab/`, `docs/` and `tests/`.
2. On GitHub, create a repository named `auction-market-lab`. Select the visibility you want. Leave initialization with a README, `.gitignore` and license unchecked, because this folder already supplies its own README and ignore file.
3. Open a terminal in the extracted folder. On Windows, Git Bash works. With Git installed and GitHub authentication configured, run the commands below. Replace `YOUR_USERNAME` with your GitHub account name.

```bash
git init -b main
git add .
git commit -m "Add RFQ auction simulator, strategies and experiments"
git remote add origin https://github.com/YOUR_USERNAME/auction-market-lab.git
git push -u origin main
```

If Git requests a commit identity, configure your own name and email with `git config user.name` and `git config user.email`, then retry the commit. Follow your installed Git credential manager's authentication flow. The commands upload the extracted source and folder structure; uploading the ZIP itself would only store an archive on the repository page.

GitHub renders the root `README.md`, its relative documentation links and the included result images. The README follows the four-part project presentation: market/API, code, strategies, and results. This archive has been prepared locally; it has not already been published to your account.

Official instructions: [Adding locally hosted code to GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).

## Run the project after cloning or extracting

Python 3.10 or newer is required. Run from the repository root:

```bash
python -m pip install -r requirements.txt
python -m auction_lab demo --players 6 --days 100 --seed 7 --out runs/six
python -m unittest discover -s tests -v
```

For all nine competitors, the stress scenario, and twenty extra independent synthetic tournaments:

```bash
python -m auction_lab demo --players 9 --days 100 --seed 7 --stress --repetitions 20 --out runs/nine
```

This second command runs 22 tournaments: one ordinary seed-7 run, one informed-customer stress run, and twenty ordinary runs with seeds 1007–1026. The report and graph are saved inside the requested output directory. Additional generated runs are ignored by Git; the curated `results/` directory is included.

## Colab

Open Google Colab, choose **File → Upload notebook**, and select `notebooks/auction_market_lab_colab.ipynb`. A CPU runtime is enough. The notebook embeds the version-0.4 source, so it also works before your repository is published. Set `INCLUDE_BENCHMARKS` and `RUN_STRESS` as desired, then run the cells in order.

Once published, you can also open the repository's notebook using Colab's GitHub tab. Repository files and the notebook use the same six-player default. Historical CSV mode is described in the notebook and `docs/01_market_and_api.md`.

## Suggested repository description

Reproducible RFQ market-making game with six strategies, three benchmark dealers, sector-specific forecasts, PCA whitening, opponent-aware quoting, and a local Python API.

Suggested topics: `market-making`, `auction-theory`, `rfq`, `quantitative-finance`, `simulation`, `python`.
