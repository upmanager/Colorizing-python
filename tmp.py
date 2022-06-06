import gdown

url = "https://drive.google.com/drive/folders/1jTsAUAKrMiHO2gn7s-fFZ_zUSzgKoPyp"
gdown.download_folder(url, quiet=True, use_cookies=False)
