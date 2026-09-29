from __future__ import annotations
import streamlit as st

from core.models.schema import Target


def render() -> tuple[Target, bytes | None, str | None] | None:
    """Returns (target, uploaded_image_bytes, uploaded_image_filename) or None.

    The image is returned as raw bytes rather than written to disk here: no
    session exists yet at this point (new_session() hasn't run), and writing
    to a fixed global temp path would leave a plaintext, never-cleaned-up
    file outside the session store's purge lifecycle. The caller writes it
    (if present) via SessionStore.temp_file_path() once a session exists.
    """
    with st.form("target_form", clear_on_submit=False):
        st.subheader("Target")
        c1, c2 = st.columns(2)
        email = c1.text_input("Email")
        phone = c2.text_input("Phone (E.164)")
        name = c1.text_input("Full name")
        username = c2.text_input("Username / handle")
        domain = c1.text_input("Domain")
        company = c2.text_input("Company")
        location = c1.text_input("Location hint")
        image = c2.file_uploader("Image (for EXIF)", type=["jpg", "jpeg", "png", "tiff"])

        submit = st.form_submit_button("Investigate", use_container_width=True)
        if submit:
            kw = {
                "email": email or None,
                "phone": phone or None,
                "name": name or None,
                "username": username or None,
                "domain": domain or None,
                "company": company or None,
                "location": location or None,
            }
            kw = {k: v for k, v in kw.items() if v}
            if not kw and not image:
                st.warning("Provide at least one identifier.")
                return None
            image_bytes = image.getvalue() if image else None
            image_name = image.name if image else None
            return Target(**kw), image_bytes, image_name
    return None
