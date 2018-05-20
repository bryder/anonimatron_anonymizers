package nz.billryder.anonimatron.anonymizer;


import com.rolfje.anonimatron.anonymizer.Anonymizer;
import com.rolfje.anonimatron.synonyms.StringSynonym;
import com.rolfje.anonimatron.synonyms.Synonym;

public class DomainAnonymizer implements Anonymizer {
    private static final String ANON_DOMAIN = ".example.com";
	private static final String TYPE = "DOMAIN";

	@Override
	public Synonym anonymize(Object from, int size) {
		StringSynonym s = new StringSynonym();
		s.setType(TYPE);
		s.setFrom(from);

		if (from == null) {
			s.setTo(null);
		} else if (from instanceof String) {
			String randomHexString = Long.toHexString(Double
					.doubleToLongBits(Math.random()));
			randomHexString += ANON_DOMAIN;

			if (randomHexString.length() > size) {
				throw new UnsupportedOperationException(
						"Can not generate domain address with length " + size
								+ ".");
			}

			s.setTo(randomHexString);
		} else {
			throw new UnsupportedOperationException(
					"Can not anonymize objects of type " + from.getClass());
		}

		return s;
	}

	@Override
	public String getType() {
		return TYPE;
	}

}

