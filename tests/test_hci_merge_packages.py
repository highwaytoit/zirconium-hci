import importlib.util
import pathlib
import unittest

root = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hci_merge", root / "build-scripts/hci-merge-packages.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def doc(packages, prefix="[Content]\nPackages=\n"):
    return (prefix + "".join(f"    {p}\n" for p in packages)).encode()


class PackageMergeTests(unittest.TestCase):
    def test_concurrent_package_additions(self):
        base = doc(["fuse", "gvfs-gphoto2", "hplip"])
        ours = doc(["fuse", "gvfs-afc", "gvfs-gphoto2", "hplip"])
        theirs = doc(["fuse", "gutenprint-cups", "gvfs-gphoto2", "hplip"])
        merged, added, removed = module.merge(base, ours, theirs)
        self.assertEqual(merged, doc(["fuse", "gutenprint-cups", "gvfs-afc", "gvfs-gphoto2", "hplip"]))
        self.assertEqual(added, {"gvfs-afc"})
        self.assertEqual(removed, set())

    def test_hci_removals_take_precedence(self):
        base = doc(["hyfetch", "nautilus", "tailscale"])
        ours = doc(["tailscale", "virt-manager"])
        theirs = doc(["hyfetch", "nautilus", "tailscale", "zbar"])
        merged, added, removed = module.merge(base, ours, theirs)
        self.assertEqual(merged, doc(["tailscale", "virt-manager", "zbar"]))
        self.assertEqual(removed, {"hyfetch", "nautilus"})
        self.assertEqual(added, {"virt-manager"})

    def test_reject_non_package_changes(self):
        base = doc(["foo"])
        ours = doc(["foo", "bar"])
        theirs = doc(["foo", "baz"], "[Content]\nRemovePackages=nautilus\nPackages=\n")
        with self.assertRaisesRegex(ValueError, "Non-package"):
            module.merge(base, ours, theirs)

    def test_reject_complex_package_lines(self):
        with self.assertRaises(ValueError):
            module.merge(doc(["foo"]), doc(["foo"]), b"[Content]\nPackages=\n    foo extra\n")

    def test_path_allowlist(self):
        self.assertTrue(module.allowed("mkosi.profiles/base-desktop/mkosi.conf.d/fedora/mkosi.conf.d/base-desktop.conf"))
        self.assertFalse(module.allowed("mkosi.postinst.chroot"))
        self.assertFalse(module.allowed("mkosi.extra/usr/bin/anything"))
        self.assertFalse(module.allowed("cosign.pub"))


if __name__ == "__main__":
    unittest.main()