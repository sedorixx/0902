def test_sklearn_installation():
    try:
        import sklearn
        from sklearn.feature_extraction.text import TfidfVectorizer
        print(f"sklearn Version: {sklearn.__version__}")
        print("TfidfVectorizer import successful")
        return True
    except ImportError as e:
        print(f"Import Error: {e}")
        return False

if __name__ == "__main__":
    test_sklearn_installation()
