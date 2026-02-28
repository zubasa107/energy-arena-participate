# Push this repository to GitHub

The repo is already initialized with one commit. Follow these steps to put it on GitHub.

---

## 1. Create a new repository on GitHub

1. Open **https://github.com/new**
2. **Repository name:** `energy-arena-participate` (or any name you like)
3. **Description:** (optional) e.g. `One-script participation in the Energy Arena — submit d-1/d-2 forecasts`
4. Choose **Public**
5. **Do not** check “Add a README”, “Add .gitignore”, or “Choose a license” (we already have these)
6. Click **Create repository**

---

## 2. Add the remote and push

In a terminal, from the **energy-arena-participate** folder, run (replace `YOUR_USERNAME` with your GitHub username):

```bash
cd C:\Arbeitsordner\00_benchmark_arena\energy-arena-participate

git remote add origin https://github.com/YOUR_USERNAME/energy-arena-participate.git
git push -u origin main
```

If your repo name is different, use it in the URL, e.g. `https://github.com/YOUR_USERNAME/your-repo-name.git`.

---

## 3. If you use SSH instead of HTTPS

```bash
git remote add origin git@github.com:YOUR_USERNAME/energy-arena-participate.git
git push -u origin main
```

---

After this, your code is on GitHub and you can share the repo URL or clone it elsewhere.
